from tools._framework import discovery


def test_fulltext_declaration_is_valid():
    found = discovery.discover()["fulltext"]
    assert found.cls is not None, found.error
