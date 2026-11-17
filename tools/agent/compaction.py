"""Keep a thread inside the model's window (GAIFA §7).

* Over 70 %: clear old function results (all but the last two steps'). They
  stay in the log; the model sees a pointer to ``read_result``.
* Over 85 %: summarize everything before the latest user message into a
  ``compact`` event; the summary moves into the system prompt.
* Still over the window in the middle of a turn (one question read more
  than fits): the oldest results are put away until the rest fits and the
  turn answers from what is left, saying it is partial (Q-091).
* Nothing left to put away: the turn stops with ``context_full``.
"""

from __future__ import annotations

from . import config, store
from .models import AgentThread

CLEAR_AT = 0.70
SUMMARIZE_AT = 0.85

SUMMARY_PROMPT = (
    "Summarize the conversation so far for yourself, so you can continue it "
    "without the full history. Keep: what the person wants and why, decisions "
    "made, facts found with their reference numbers (#n), open questions. "
    "Under 300 words. Plain text."
)


def window() -> int:
    """``[tools.agent] context_window`` when the host set one; otherwise what
    chat's server reports for its model (32768 when it reports nothing)."""
    stated = int(config.get("context_window") or 0)
    if stated > 0:
        return stated
    from apps.core import llm_servers

    from .llmcall import model_name, route

    current = route()
    return llm_servers.context_window(current.server, model_name(current))


def clear_old_results(thread: AgentThread, events) -> bool:
    steps = [e for e in events if e.type == "assistant" and e.payload.get("tool_calls")]
    keep_ids = set()
    for e in steps[-2:]:
        keep_ids |= {c["id"] for c in e.payload.get("tool_calls", [])}
    cleared = set((thread.settings or {}).get("cleared", []))
    before = len(cleared)
    for e in events:
        if e.type == "tool_result" and e.payload.get("call_id") not in keep_ids:
            cleared.add(e.payload.get("call_id"))
    if len(cleared) == before:
        return False
    # Only this key: the references and loaded functions the turn's calls
    # wrote meanwhile stay as they are.
    store.save_setting(
        thread,
        "cleared",
        lambda now: sorted({c for c in [*(now or []), *cleared] if c}),
    )
    return True


def clear_to_fit(thread: AgentThread, events, over: int) -> bool:
    """Put results away, oldest first, until about ``over`` tokens are freed.
    False when nothing was left to put away."""
    from . import rebuild

    cleared = set((thread.settings or {}).get("cleared", []))
    pointer = len(rebuild.result_text({"call_id": "x" * 24}, cleared=True))
    put_away, freed = [], 0
    for e in events:
        call_id = e.payload.get("call_id")
        if e.type != "tool_result" or not call_id or call_id in cleared:
            continue
        if freed >= over:
            break
        size = len(rebuild.result_text(e.payload))
        if size <= pointer:
            continue  # an error or a short result: the pointer is no shorter
        put_away.append(call_id)
        freed += (size - pointer) // rebuild.CHARS_PER_TOKEN
    if not put_away:
        return False
    store.save_setting(
        thread,
        "cleared",
        lambda now: sorted({c for c in [*(now or []), *put_away] if c}),
    )
    return True


def summarize(thread: AgentThread, events, port, build_messages) -> bool:
    users = [e for e in events if e.type == "user"]
    if len(users) < 2:
        return False
    upto = users[-1].seq - 1
    older = [e for e in events if e.seq <= upto]
    history = build_messages(thread, older)
    if not history:
        return False
    reply = port(
        messages=[
            {"role": "system", "content": SUMMARY_PROMPT},
            *history,
            {"role": "user", "content": SUMMARY_PROMPT},
        ],
        tools=None,
        tool_choice=None,
        on_delta=None,
        should_stop=None,
    )
    text = (reply.content or "").strip()
    if not text:
        return False
    store.append(thread, "compact", {"summary": text, "upto_seq": upto})
    return True


def latest_summary(events) -> str:
    summary = ""
    for e in events:
        if e.type == "compact":
            summary = e.payload.get("summary", "")
    return summary
