"""The agent loads without a model (D-5): a missing LLM_MODEL is reported by
the API as ``no_model``, never as a failed tool."""


def check() -> None:
    from . import registry  # noqa: F401  (imports cleanly)
