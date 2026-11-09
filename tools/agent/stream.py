"""Live streaming: every stored event and every transient delta goes to a
Redis pub/sub channel per thread (``agent:t:<thread>``) and per person
(``agent:u:<user>``). The SSE view and in-process subscribers (the CLI now,
Discord later) read the same channels.

Stored events carry their ``seq`` as the SSE ``id``; a client reconnecting with
``Last-Event-ID`` gets every stored event after it, then live ones. Transient
events (text and thinking deltas, progress, the context meter) carry no id and
are never stored: the ``assistant`` event that follows holds the whole text.

The bus is Redis (database ``tools.agent.redis_db``). If Redis cannot be
reached the process falls back to an in-memory bus, which serves subscribers in
the same process only; tests install it explicitly with :func:`use_memory_bus`.
"""

from __future__ import annotations

import json
import logging
import queue
import re
import threading
import time
from collections.abc import Iterator

from django.conf import settings

logger = logging.getLogger(__name__)

HEARTBEAT_SECONDS = 15


def thread_channel(thread_id) -> str:
    return f"agent:t:{thread_id}"


def user_channel(user_id) -> str:
    return f"agent:u:{user_id}"


# --------------------------------------------------------------------------- #
# Buses
# --------------------------------------------------------------------------- #


class MemoryBus:
    """In-process pub/sub and flags."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: dict[str, list[queue.Queue]] = {}
        self._flags: dict[str, float] = {}

    def publish(self, channel: str, message: dict) -> None:
        with self._lock:
            targets = list(self._subs.get(channel, ()))
        for q in targets:
            q.put(message)

    def subscribe(self, channels: list[str]) -> Subscription:
        q: queue.Queue = queue.Queue()
        with self._lock:
            for ch in channels:
                self._subs.setdefault(ch, []).append(q)

        def close() -> None:
            with self._lock:
                for ch in channels:
                    if q in self._subs.get(ch, []):
                        self._subs[ch].remove(q)

        def get(timeout: float):
            try:
                return q.get(timeout=timeout)
            except queue.Empty:
                return None

        return Subscription(get, close)

    def set_flag(self, key: str, ttl: int = 3600) -> None:
        self._flags[key] = time.time() + ttl

    def has_flag(self, key: str) -> bool:
        until = self._flags.get(key)
        return bool(until and until > time.time())

    def clear_flag(self, key: str) -> None:
        self._flags.pop(key, None)


class RedisBus:
    def __init__(self, url: str) -> None:
        import redis

        self._client = redis.Redis.from_url(
            url, socket_connect_timeout=2, socket_timeout=5
        )
        self._client.ping()

    def publish(self, channel: str, message: dict) -> None:
        self._client.publish(channel, json.dumps(message, default=str))

    def subscribe(self, channels: list[str]) -> Subscription:
        pubsub = self._client.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(*channels)

        def get(timeout: float):
            msg = pubsub.get_message(timeout=timeout)
            if not msg or msg.get("type") != "message":
                return None
            try:
                return json.loads(msg["data"])
            except (TypeError, ValueError):
                return None

        return Subscription(get, pubsub.close)

    def set_flag(self, key: str, ttl: int = 3600) -> None:
        self._client.set(key, "1", ex=ttl)

    def has_flag(self, key: str) -> bool:
        return bool(self._client.exists(key))

    def clear_flag(self, key: str) -> None:
        self._client.delete(key)


class Subscription:
    def __init__(self, get, close) -> None:
        self.get = get
        self.close = close


def redis_url() -> str:
    from . import config

    db = int(config.get("redis_db"))
    base = getattr(settings, "REDIS_URL", "") or getattr(
        settings, "CELERY_BROKER_URL", ""
    )
    base = base or "redis://localhost:6379/0"
    if re.search(r"/\d+$", base):
        return re.sub(r"/\d+$", f"/{db}", base)
    return base.rstrip("/") + f"/{db}"


_bus = None


def bus():
    global _bus
    if _bus is None:
        try:
            _bus = RedisBus(redis_url())
        except Exception as exc:  # degrade to one process rather than fail turns
            logger.warning("agent stream: Redis unavailable (%s); in-process only", exc)
            _bus = MemoryBus()
    return _bus


def use_memory_bus() -> MemoryBus:
    """Install a fresh in-memory bus (tests)."""
    global _bus
    _bus = MemoryBus()
    return _bus


# --------------------------------------------------------------------------- #
# Publishing
# --------------------------------------------------------------------------- #


def event_message(event) -> dict:
    return {
        "id": event.seq,
        "type": event.type,
        "thread": str(event.thread_id),
        "payload": event.payload,
        "ts": event.ts.isoformat() if event.ts else None,
    }


def _send(thread_id, user_id, message: dict) -> None:
    try:
        b = bus()
        b.publish(thread_channel(thread_id), message)
        if user_id is not None:
            b.publish(user_channel(user_id), message)
    except Exception:  # streaming is a view of the log; never break a turn
        logger.exception("agent stream: publish failed")


def publish_event(event) -> None:
    user_id = getattr(event.thread, "user_id", None)
    _send(event.thread_id, user_id, event_message(event))


def publish_transient(thread, type_: str, **data) -> None:
    _send(thread.pk, thread.user_id, {"type": type_, "thread": str(thread.pk), **data})


# --------------------------------------------------------------------------- #
# Cancel
# --------------------------------------------------------------------------- #


def _cancel_key(thread_id) -> str:
    return f"agent:cancel:{thread_id}"


def request_cancel(thread_id) -> None:
    bus().set_flag(_cancel_key(thread_id))


def cancel_requested(thread_id) -> bool:
    try:
        return bus().has_flag(_cancel_key(thread_id))
    except Exception:
        return False


def clear_cancel(thread_id) -> None:
    try:
        bus().clear_flag(_cancel_key(thread_id))
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Reading: replay then tail
# --------------------------------------------------------------------------- #


def follow(
    thread,
    *,
    after: int = 0,
    follow_live: bool = True,
    max_seconds: float | None = None,
    poll: float = 1.0,
    stop_when_idle: bool = False,
) -> Iterator[dict]:
    """Stored events after ``after``, then live messages, with no gap and no
    duplicate: subscribe first, replay from the database, then drop any live
    stored event whose seq was already sent. Yields ``{"type": "heartbeat"}``
    every ``HEARTBEAT_SECONDS`` of silence."""
    from . import store
    from .models import AgentThread

    sub = bus().subscribe([thread_channel(thread.pk)]) if follow_live else None
    sent = after
    try:
        for event in store.events(thread, after=after):
            sent = event.seq
            yield event_message(event)
        if sub is None:
            return
        started = last = time.monotonic()
        while True:
            if max_seconds is not None and time.monotonic() - started > max_seconds:
                return
            msg = sub.get(poll)
            now = time.monotonic()
            if msg is None:
                if stop_when_idle:
                    state = (
                        AgentThread.objects.filter(pk=thread.pk)
                        .values_list("state", flat=True)
                        .first()
                    )
                    if state != "running":
                        # catch anything stored after the last live message
                        for event in store.events(thread, after=sent):
                            sent = event.seq
                            yield event_message(event)
                        return
                if now - last >= HEARTBEAT_SECONDS:
                    last = now
                    yield {"type": "heartbeat"}
                continue
            last = now
            seq = msg.get("id")
            if seq is not None:
                if seq <= sent:
                    continue
                if seq > sent + 1:  # a gap: fill it from the log
                    for event in store.events(thread, after=sent, upto=seq - 1):
                        sent = event.seq
                        yield event_message(event)
                sent = seq
            yield msg
    finally:
        if sub is not None:
            sub.close()


def sse_format(message: dict) -> str:
    if message.get("type") == "heartbeat":
        return ": heartbeat\n\n"
    lines = []
    if message.get("id") is not None:
        lines.append(f"id: {message['id']}")
    lines.append(f"event: {message.get('type', 'message')}")
    lines.append("data: " + json.dumps(message, default=str))
    return "\n".join(lines) + "\n\n"
