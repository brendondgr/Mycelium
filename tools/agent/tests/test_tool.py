from tools._framework import discovery


def test_agent_declaration_is_valid():
    found = discovery.discover()["agent"]
    assert found.cls is not None, found.error
