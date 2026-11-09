"""The vendored ``llmkit`` package passes its own offline self-test.

``apps/core/llmkit/selftest.py`` is the skill's ``scripts/selftest.py``: mock
vLLM, llama.cpp and Ollama servers on loopback, plus offline shape checks for
the Anthropic and Gemini adapters. It needs no key and no network.
"""

from apps.core.llmkit import selftest


def test_vendored_llmkit_selftest_passes(capsys):
    code = selftest.main(["--quiet"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert selftest.FAIL == 0
    assert selftest.PASS >= 100


def test_vendored_llmkit_imports_no_agent_loop():
    import apps.core.llmkit as kit

    assert not hasattr(kit, "run_tools")
    assert kit.Registry and kit.ProviderConfig
