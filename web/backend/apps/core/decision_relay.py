"""Forward a decision server on the host's loopback to Mycelium's containers.

    python -m apps.core.decision_relay   # from web/backend; the decision-relay service

The backend asks the decision model from inside its container, where the host's
127.0.0.1 is out of reach, and a server such as GAIFA's decide listens only
there. With ``[decision] port_relay = true`` the ``decision-relay`` service
(host network) listens on the Docker bridge address that ``host.docker.internal``
names, on ``port_url``'s port, and pipes each connection to the same port on
127.0.0.1. Nothing changes on the decision server's side.

Only the standard library and ``config.instance`` are imported, so the service
runs on plain Python without the backend's dependencies. Off, misconfigured,
or with the address taken, it says why and idles rather than restart-looping.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import socket
import sys
from pathlib import Path
from urllib.parse import urlsplit

BACKEND = Path(__file__).resolve().parents[2]


def _load_instance():
    """``config/instance.py`` by path: the ``config`` package's ``__init__``
    starts Celery, which this service has no reason to install."""
    name = "config.instance"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        "mycelium_instance", BACKEND / "config" / "instance.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up here
    spec.loader.exec_module(module)
    return module


I = _load_instance()  # noqa: E741

BRIDGE_NAME = "host.docker.internal"
CHUNK = 64 * 1024


class RelayOff(Exception):
    """Why the relay has nothing to do; it idles with this message."""


def target_port(values) -> int:
    """The port to forward, from ``[decision]``; RelayOff when there is none."""
    if not values["decision.port_relay"]:
        raise RelayOff("[decision] port_relay is off")
    url = urlsplit(values["decision.port_url"])
    if url.hostname != BRIDGE_NAME:
        raise RelayOff(
            f"[decision] port_url must be http://{BRIDGE_NAME}:<port> "
            f"(it is {values['decision.port_url']!r})"
        )
    return url.port or (443 if url.scheme == "https" else 80)


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(CHUNK):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.IncompleteReadError):
        pass
    finally:
        if not writer.is_closing():
            writer.close()


def handler(target_host: str, port: int):
    async def handle(reader, writer):
        try:
            up_reader, up_writer = await asyncio.open_connection(target_host, port)
        except OSError as exc:
            print(f"decision-relay: {target_host}:{port} refused ({exc})", flush=True)
            writer.close()
            return
        await asyncio.gather(_pipe(reader, up_writer), _pipe(up_reader, writer))

    return handle


async def serve(listen: str, port: int, target_host: str = "127.0.0.1"):
    """A started server forwarding ``listen:port`` to ``target_host:port``."""
    return await asyncio.start_server(
        handler(target_host, port), listen, port, reuse_address=True
    )


async def _idle(reason: str) -> None:
    print(f"decision-relay: {reason}; idling.", flush=True)
    await asyncio.Event().wait()


async def main() -> None:
    values = I.resolve(BACKEND.parents[1], os.environ)
    try:
        port = target_port(values)
        listen = socket.gethostbyname(BRIDGE_NAME)
    except RelayOff as exc:
        return await _idle(str(exc))
    except OSError as exc:
        return await _idle(f"cannot resolve {BRIDGE_NAME} ({exc})")
    try:
        server = await serve(listen, port)
    except OSError as exc:
        return await _idle(f"cannot listen on {listen}:{port} ({exc})")
    print(
        f"decision-relay: {listen}:{port} -> 127.0.0.1:{port} "
        f"({BRIDGE_NAME}:{port} from the containers)",
        flush=True,
    )
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
