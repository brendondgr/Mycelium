"""``manage.py agent chat --user <name> --scope personal|lab:<slug>|project:<uuid>``

The developer's way to drive the whole backend before any UI exists: opens or
resumes a thread, streams Mylo's reply, renders ask_user as a numbered prompt.
In the chat: ``/attach <path>``, ``/cancel``, ``/fork <seq>``, ``/export``,
``/quit``. ``--message`` sends one message and exits (the evaluation runner
uses the same service calls).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Chat with Mylo from the terminal (operator tool)."

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="action", required=True)
        chat = sub.add_parser("chat")
        chat.add_argument("--user", required=True)
        chat.add_argument("--scope", default="personal")
        chat.add_argument("--thread", default="")
        chat.add_argument("--message", default="")
        sub.add_parser("catalog").add_argument("--user", required=True)

    def handle(self, *args, **opts):
        from tools.agent import service
        from tools.agent.surfaces import cli

        try:
            user = User.objects.get(username=opts["user"])
        except User.DoesNotExist:
            raise CommandError(f"no user {opts['user']!r}") from None
        if opts["action"] == "catalog":
            for row in service.catalog_view(cli.caller(user)):
                mark = "✓" if row["allowed"] else "✗"
                self.stdout.write(f"{mark} {row['name']:<24} {row.get('detail') or ''}")
            return
        kind, _, ref = opts["scope"].partition(":")
        if opts["thread"]:
            thread = service.get_thread(user, opts["thread"])
        else:
            scope = service.scope_from(user, kind, ref or None)
            thread = service.create_thread(user, scope=scope, surface="cli")
        self.stdout.write(f"thread {thread.pk} ({thread.scope_kind})")
        if opts["message"]:
            self._send(user, thread, opts["message"], [])
            return
        attachments: list = []
        while True:
            try:
                line = input("you> ").strip()
            except EOFError:
                break
            if not line:
                continue
            if line in ("/quit", "/exit"):
                break
            if line.startswith("/attach "):
                path = Path(line.split(" ", 1)[1]).expanduser()
                attachments.append(SimpleUploadedFile(path.name, path.read_bytes()))
                self.stdout.write(
                    f"(attached {path.name}; it goes with your next message)"
                )
                continue
            if line == "/cancel":
                service.cancel(cli.caller(user, thread), thread)
                continue
            if line.startswith("/fork "):
                thread = service.fork_thread(user, thread.pk, int(line.split()[1]))
                self.stdout.write(f"forked into {thread.pk}")
                continue
            if line == "/export":
                self.stdout.write(
                    service.export(cli.caller(user, thread), thread, fmt="md")
                )
                continue
            self._send(user, thread, line, attachments)
            attachments = []

    def _send(self, user, thread, text, attachments):
        """Run the turn here, in this process, printing text as it streams
        (a listener on the live channel) and the rest from the log after."""
        from tools.agent import loop, service, store, stream
        from tools.agent.surfaces import cli

        caller = cli.caller(user, thread)
        after = store.last_seq(thread)
        thread.refresh_from_db()
        if thread.state == "waiting":
            service.answer(caller, thread, text, start=lambda t: None)
        else:
            service.send(
                caller, thread, text, attachments=attachments, start=lambda t: None
            )
        sub = stream.bus().subscribe([stream.thread_channel(thread.pk)])
        done = threading.Event()
        streamed = []

        def listen():
            while not done.is_set():
                msg = sub.get(0.2)
                if msg and msg.get("type") == "delta" and msg.get("kind") == "text":
                    streamed.append(msg.get("text", ""))
                    self.stdout.write(msg.get("text", ""), ending="")
                    self.stdout.flush()

        listener = threading.Thread(target=listen, daemon=True)
        listener.start()
        try:
            loop.run_turn(thread.pk)
        finally:
            done.set()
            listener.join(timeout=2)
            sub.close()
        for event in store.events(thread, after=after):
            self._render(event, streamed=bool(streamed))

    def _render(self, event, *, streamed):
        payload = event.payload or {}
        if event.type == "assistant" and payload.get("final"):
            self.stdout.write("\n" if streamed else payload.get("text", ""))
        elif event.type == "tool_call":
            self.stdout.write(
                f"  · {payload.get('name')}({json.dumps(payload.get('args'))})"
            )
        elif event.type == "question":
            self.stdout.write(f"Mylo asks: {payload.get('question')}")
            for i, option in enumerate(payload.get("options") or [], 1):
                self.stdout.write(f"  {i}. {option}")
        elif event.type in ("error", "note"):
            self.stdout.write(
                f"[{event.type}] {payload.get('detail') or payload.get('text')}"
            )
