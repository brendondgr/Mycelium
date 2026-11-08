from tools._framework.tests.fixtures.ok_leaf.read import greeting


def shout() -> str:
    return greeting().upper()
