from tools._framework import discovery


def test_files_declaration_is_valid():
    found = discovery.discover()["files"]
    assert found.cls is not None, found.error
