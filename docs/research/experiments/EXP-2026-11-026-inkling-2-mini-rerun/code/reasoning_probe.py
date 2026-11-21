"""EXP-2026-11-026 side check: which reasoning controls does the served model obey?

Sends one fixed question three times under each request variant and records
the reasoning and completion tokens the server reports. Variants: what Mylo
sends today (``enable_thinking: false`` + ``thinking_token_budget: 512``),
nothing, ``enable_thinking`` on/off alone, vLLM's ``reasoning_effort``
low/medium/high, and a small ``thinking_token_budget``. Prints JSON lines.
Standard library only; run where the relay is reachable (the backend
container):

    docker compose exec -T backend python3 - < …/code/reasoning_probe.py > data/reasoning_probe.jsonl
"""

import json
import os
import time
import urllib.request

BASE = os.environ.get("LLM_BASE_URL", "http://llm-tunnel:9090/v1").rstrip("/")
MODEL = "default-model"
QUESTION = ("A lab has 5 members and 3 projects. Each project needs 2 members and no member may be on "
            "more than 2 projects. Is an assignment possible? Answer yes or no with one sentence.")
VARIANTS = {
    "mylo_today": {"chat_template_kwargs": {"enable_thinking": False}, "thinking_token_budget": 512},
    "nothing": {},
    "enable_thinking_false": {"chat_template_kwargs": {"enable_thinking": False}},
    "enable_thinking_true": {"chat_template_kwargs": {"enable_thinking": True}},
    "effort_low": {"reasoning_effort": "low"},
    "effort_medium": {"reasoning_effort": "medium"},
    "effort_high": {"reasoning_effort": "high"},
    "budget_64": {"thinking_token_budget": 64},
}


def ask(extra):
    body = {"model": MODEL, "max_tokens": 6000, "temperature": 0.2,
            "messages": [{"role": "user", "content": QUESTION}], **extra}
    req = urllib.request.Request(f"{BASE}/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.loads(r.read())
    msg = d["choices"][0]["message"]
    u = d.get("usage") or {}
    return {"seconds": round(time.monotonic() - t0, 2), "finish": d["choices"][0].get("finish_reason"),
            "completion_tokens": u.get("completion_tokens"),
            "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
            "reasoning_chars": len(msg.get("reasoning") or msg.get("reasoning_content") or ""),
            "content": (msg.get("content") or "")[:200]}


for name, extra in VARIANTS.items():
    for rep in range(3):
        try:
            row = ask(extra)
        except Exception as exc:  # noqa: BLE001
            row = {"error": f"{type(exc).__name__}: {exc}"[:300]}
        print(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "variant": name,
                          "sent": extra, "rep": rep, **row}), flush=True)
