"""The decision relay (`[decision] port_relay`): what it forwards, and that it does."""

from __future__ import annotations

import asyncio
import socket

import pytest

from apps.core import decision_relay as R
from config import instance as I


def values(**file):
    return I.resolve(I.Path("/nowhere"), {}, file_values=file)


def test_off_by_default():
    with pytest.raises(R.RelayOff, match="off"):
        R.target_port(values())


def test_port_comes_from_port_url():
    v = values(**{"decision.port_relay": True,
                  "decision.port_url": "http://host.docker.internal:5107"})
    assert R.target_port(v) == 5107


def test_a_url_elsewhere_is_refused_and_flagged():
    v = values(**{"decision.port_relay": True,
                  "decision.port_url": "http://10.0.0.5:5107"})
    with pytest.raises(R.RelayOff, match="host.docker.internal"):
        R.target_port(v)
    assert any("port_relay" in p for p in v.problems({}))


def test_bytes_go_both_ways():
    async def run():
        async def echo(reader, writer):
            writer.write(b"pong:" + await reader.read(100))
            await writer.drain()
            writer.close()

        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        upstream = await asyncio.start_server(echo, "127.0.0.1", port)
        # The relay listens on another loopback address, on the same port, as it
        # listens on the bridge address in the stack.
        relay = await R.serve("127.0.0.2", port, target_host="127.0.0.1")
        async with upstream, relay:
            reader, writer = await asyncio.open_connection("127.0.0.2", port)
            writer.write(b"ping")
            await writer.drain()
            got = await asyncio.wait_for(reader.read(100), 5)
            writer.close()
        return got

    assert asyncio.run(run()) == b"pong:ping"
