"""The agent loads without a model (D-5): a missing LLM_MODEL is reported by
the API as ``no_model``, never as a failed tool. Likewise a model server that
is down never fails the tool's load; :func:`report` says which server chat
uses, where it runs and whether it answers."""


def check() -> None:
    from . import registry  # noqa: F401  (imports cleanly)


def report(*, force: bool = False) -> dict:
    """``{server, model, label, location, answers, error, problem}`` for chat.

    ``problem`` is set when ``llm.routes.agent`` was not honoured (an unknown
    or disabled server, or a cloud one while ``llm.allow_cloud`` is false).
    Asks the server's model listing (cached); never raises."""
    from apps.core import llm_servers

    from .llmcall import model_info, route

    current = route()
    info = model_info(current) or {}
    answers, error = llm_servers.health(current.server, force=force)
    return {
        "server": current.server,
        "model": info.get("name") or None,
        "label": info.get("label") or current.label,
        "location": current.location,
        "answers": answers,
        "error": error,
        "problem": current.problem or None,
    }
