"""Forward servers on the host's loopback to Mycelium's containers: the
decision server, and (``[llm] port_relay``) the model server.

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
import ipaddress
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


def llm_port(values, environ) -> int:
    """The model server's port to forward, from ``[llm] port_relay`` and
    ``LLM_BASE_URL``; RelayOff when there is none."""
    if not values["llm.port_relay"]:
        raise RelayOff("[llm] port_relay is off")
    base = str(environ.get("LLM_BASE_URL", ""))
    url = urlsplit(base)
    if url.hostname != BRIDGE_NAME:
        raise RelayOff(
            f"LLM_BASE_URL must be http://{BRIDGE_NAME}:<port>/v1 (it is {base!r})"
        )
    return url.port or (443 if url.scheme == "https" else 80)


def target_ports(values, environ) -> tuple[list[int], list[str]]:
    """Every port to forward (the decision server's, the model server's), and
    why each of the others is not."""
    ports, reasons = [], []
    for find in (lambda: target_port(values), lambda: llm_port(values, environ)):
        try:
            port = find()
        except RelayOff as exc:
            reasons.append(str(exc))
        else:
            if port not in ports:
                ports.append(port)
    return ports, reasons


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


#: Docker's default address pools for bridge networks. Every container on the
#: host can reach the bridge address, not only Mycelium's, so on a shared
#: server set DECISION_RELAY_ALLOW to this stack's own network
#: (`docker network inspect <project>_default`) — see docs/configuration.md.
DEFAULT_ALLOW = "172.16.0.0/12,192.168.0.0/16"


def allowed_networks(environ) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """The peer ranges the relay accepts, from ``DECISION_RELAY_ALLOW``."""
    raw = str(environ.get("DECISION_RELAY_ALLOW", "") or DEFAULT_ALLOW)
    return [
        ipaddress.ip_network(part.strip(), strict=False)
        for part in raw.split(",")
        if part.strip()
    ]


def peer_allowed(peer, networks) -> bool:
    """Whether a connection's peer address is inside one of ``networks``."""
    try:
        address = ipaddress.ip_address(peer[0] if isinstance(peer, tuple) else peer)
    except (TypeError, ValueError, IndexError):
        return False
    return any(address in network for network in networks)


def handler(target_host: str, port: int, networks=None):
    networks = networks if networks is not None else allowed_networks(os.environ)

    async def handle(reader, writer):
        peer = writer.get_extra_info("peername")
        if not peer_allowed(peer, networks):
            print(f"decision-relay: refused a connection from {peer!r}", flush=True)
            writer.close()
            return
        try:
            up_reader, up_writer = await asyncio.open_connection(target_host, port)
        except OSError as exc:
            print(f"decision-relay: {target_host}:{port} refused ({exc})", flush=True)
            writer.close()
            return
        await asyncio.gather(_pipe(reader, up_writer), _pipe(up_reader, writer))

    return handle


async def serve(
    listen: str, port: int, target_host: str = "127.0.0.1", networks=None
):
    """A started server forwarding ``listen:port`` to ``target_host:port``,
    for peers inside ``networks`` (default: ``allowed_networks``)."""
    return await asyncio.start_server(
        handler(target_host, port, networks), listen, port, reuse_address=True
    )


async def _idle(reason: str) -> None:
    print(f"decision-relay: {reason}; idling.", flush=True)
    await asyncio.Event().wait()


async def main() -> None:
    values = I.resolve(BACKEND.parents[1], os.environ)
    ports, reasons = target_ports(values, os.environ)
    for reason in reasons:
        print(f"decision-relay: {reason}", flush=True)
    if not ports:
        return await _idle("nothing to forward")
    try:
        listen = socket.gethostbyname(BRIDGE_NAME)
    except OSError as exc:
        return await _idle(f"cannot resolve {BRIDGE_NAME} ({exc})")
    servers = []
    for port in ports:
        try:
            servers.append(await serve(listen, port))
        except OSError as exc:
            print(
                f"decision-relay: cannot listen on {listen}:{port} ({exc})",
                flush=True,
            )
            continue
        print(
            f"decision-relay: {listen}:{port} -> 127.0.0.1:{port} "
            f"({BRIDGE_NAME}:{port} from the containers)",
            flush=True,
        )
    if not servers:
        return await _idle("no port could be opened")
    await asyncio.gather(*(server.serve_forever() for server in servers))


if __name__ == "__main__":
    asyncio.run(main())
