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


def test_the_model_server_port_is_forwarded_when_asked():
    env = {"LLM_BASE_URL": "http://host.docker.internal:9090/v1"}
    assert R.target_ports(values(), env)[0] == []
    v = values(**{"llm.port_relay": True})
    assert R.target_ports(v, env)[0] == [9090]
    both = values(**{"llm.port_relay": True, "decision.port_relay": True,
                     "decision.port_url": "http://host.docker.internal:5107"})
    assert R.target_ports(both, env)[0] == [5107, 9090]


def test_a_model_url_elsewhere_is_not_forwarded_and_is_flagged():
    v = values(**{"llm.port_relay": True})
    env = {"LLM_BASE_URL": "http://10.0.0.5:9090/v1"}
    ports, reasons = R.target_ports(v, env)
    assert ports == [] and any("LLM_BASE_URL" in r for r in reasons)
    assert any("llm.port_relay" in p for p in v.problems(env))


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
        relay = await R.serve(
            "127.0.0.2",
            port,
            target_host="127.0.0.1",
            networks=R.allowed_networks({"DECISION_RELAY_ALLOW": "127.0.0.0/8"}),
        )
        async with upstream, relay:
            reader, writer = await asyncio.open_connection("127.0.0.2", port)
            writer.write(b"ping")
            await writer.drain()
            got = await asyncio.wait_for(reader.read(100), 5)
            writer.close()
        return got

    assert asyncio.run(run()) == b"pong:ping"


def test_a_peer_outside_the_allowed_networks_is_refused():
    async def run():
        async def echo(reader, writer):
            writer.write(b"pong")
            await writer.drain()
            writer.close()

        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        upstream = await asyncio.start_server(echo, "127.0.0.1", port)
        # Only Docker bridge ranges are allowed, so a loopback peer is refused.
        relay = await R.serve(
            "127.0.0.2",
            port,
            target_host="127.0.0.1",
            networks=R.allowed_networks({}),
        )
        async with upstream, relay:
            reader, writer = await asyncio.open_connection("127.0.0.2", port)
            got = await asyncio.wait_for(reader.read(100), 5)
            writer.close()
        return got

    assert asyncio.run(run()) == b""


def test_allowed_networks_reads_the_env_and_defaults_to_docker_pools():
    default = R.allowed_networks({})
    assert R.peer_allowed(("172.18.0.5", 1234), default)
    assert not R.peer_allowed(("10.1.2.3", 1234), default)
    narrow = R.allowed_networks({"DECISION_RELAY_ALLOW": "172.29.0.0/24"})
    assert R.peer_allowed(("172.29.0.9", 1), narrow)
    assert not R.peer_allowed(("172.18.0.5", 1), narrow)
    assert not R.peer_allowed(None, narrow)
