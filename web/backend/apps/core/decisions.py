"""Decision models behind one switch: hosted Jev, any model on a port, or none.

A *decision* is a typed question about a piece of state answered with a
probability — never a sentence. :mod:`apps.core.systemone` is the client for
TypeSafe's hosted Jev; this module puts it behind a backend switch together with
a decision model the operator runs themselves, so the slate rerank (and anything
else that asks typed questions) does not care where the answer came from.

``[decision] backend`` in ``mycelium.toml`` (``DECISION_BACKEND``) chooses:

* ``jev`` — TypeSafe's hosted model. Needs ``TYPESAFE_API_KEY``; sends the state
  off the host.
* ``port`` — whatever answers at ``[decision] port_url``. Nothing leaves the
  operator's network. Two wire protocols, detected from ``GET /v1/models``:

  - ``decide`` — a decision server (GAIFA's ``decide`` mod: d3-lite today, any
    adapter it gains later). ``POST /v1/decide`` takes the questions natively and
    returns a probability per answer.
  - ``openai`` — any OpenAI-compatible server (llama.cpp's ``llama-server``,
    vLLM) running an instruct model. Each question is one chat completion with
    ``max_tokens=1`` and ``top_logprobs``; the answer is the softmax of the
    allowed answers' first-token log-probabilities, thinking switched off.
    Meant for a model trained to decide (a fine-tuned student): a stock
    instruct model answers with saturated, uncalibrated probabilities and gives
    no ordering (Qwen3-4B: ``worth`` >= 0.999995 on every pair,
    ``EXP-2026-11-009``).

* ``off`` — no decision model. Callers keep their own deterministic order.
* ``auto`` (the default) — ``jev`` when a TypeSafe key is set, else ``port``
  when a port URL is set, else ``off``. An instance that configures nothing gets
  the plain filtering stack and sends nothing anywhere.

The old ``RERANK_METHOD`` values still mean what they meant: ``typesafe`` is
``jev`` and ``local`` is ``off``.

Questions are plain dicts built with :func:`yesno`, :func:`score` and
:func:`choice`; every backend returns answers in the shape
:func:`apps.core.systemone.answer_to_dict` produces (``noul`` for a yes/no;
``score``, ``probabilities`` keyed ``"0".."n"`` and ``confidence`` for a score;
``choice`` and ``probabilities`` for a choice), so a stored judgement reads the
same whichever backend wrote it. Every call is counted in the LLM ledger under
the caller's ``component``.
"""

from __future__ import annotations

import json
import logging
import math
import string
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from apps.core import llm_usage

logger = logging.getLogger(__name__)

AUTO, JEV, PORT, OFF = "auto", "jev", "port", "off"
BACKENDS = (AUTO, JEV, PORT, OFF)
#: Values ``RERANK_METHOD`` used to take, and what they mean now.
LEGACY = {"typesafe": JEV, "local": OFF}

PROTOCOL_AUTO, PROTOCOL_DECIDE, PROTOCOL_OPENAI = "auto", "decide", "openai"
PROTOCOLS = (PROTOCOL_AUTO, PROTOCOL_DECIDE, PROTOCOL_OPENAI)

#: The OpenAI-compatible path can only read single-token answers.
_CHOICE_LABELS = string.ascii_uppercase
_TOP_LOGPROBS = 20


class DecisionError(RuntimeError):
    """A decision could not be made (unreachable, unparseable, refused)."""


# --------------------------------------------------------------------------- #
# Backend resolution
# --------------------------------------------------------------------------- #


def _setting(settings: Any, name: str, default: Any = "") -> Any:
    return getattr(settings, name, default)


def normalise(value: Any) -> str:
    """The configured backend name, legacy spellings mapped; unknown is ``off``."""
    text = str(value or "").strip().lower()
    text = LEGACY.get(text, text)
    if text not in BACKENDS:
        logger.warning(
            "decision backend %r is not one of %s; using off", value, BACKENDS
        )
        return OFF
    return text


def configured(settings: Any | None = None) -> str:
    """``DECISION_BACKEND`` as configured (``auto`` included)."""
    settings = _django(settings)
    return normalise(_setting(settings, "DECISION_BACKEND", AUTO))


def resolve(settings: Any | None = None) -> tuple[str, str]:
    """``(backend, reason)`` — the backend that will actually answer.

    ``backend`` is ``jev``, ``port`` or ``off``. A backend chosen explicitly but
    missing what it needs resolves to ``off`` and ``reason`` says why, so the
    caller can log it once instead of failing the nightly run.
    """
    settings = _django(settings)
    chosen = configured(settings)
    has_key = bool(_setting(settings, "TYPESAFE_API_KEY", ""))
    has_url = bool(str(_setting(settings, "DECISION_PORT_URL", "")).strip())
    if chosen == AUTO:
        if has_key:
            return JEV, "auto: TYPESAFE_API_KEY is set"
        if has_url:
            return PORT, "auto: [decision] port_url is set"
        return OFF, "auto: no TypeSafe key and no port URL configured"
    if chosen == JEV and not has_key:
        return OFF, "backend = jev but TYPESAFE_API_KEY is empty"
    if chosen == PORT and not has_url:
        return OFF, "backend = port but [decision] port_url is empty"
    return chosen, f"backend = {chosen}"


def _django(settings: Any | None) -> Any:
    if settings is not None:
        return settings
    from django.conf import settings as django_settings

    return django_settings


# --------------------------------------------------------------------------- #
# Questions — plain data, so no caller imports an SDK to ask
# --------------------------------------------------------------------------- #


def yesno(
    instructions: str, *, true: str | None = None, false: str | None = None
) -> dict:
    """A yes/no question; the answer is ``{"noul": p(yes)}``."""
    return {"type": "yesno", "instructions": instructions, "true": true, "false": false}


def score(instructions: str, levels: Sequence[str]) -> dict:
    """An ordered scale, 2 to 10 levels, lowest first. The answer's ``score`` is
    the probability-weighted level index."""
    levels = [str(level) for level in levels]
    if not 2 <= len(levels) <= 10:
        raise ValueError("a score needs 2 to 10 levels")
    return {"type": "score", "instructions": instructions, "levels": levels}


def choice(instructions: str, options: Mapping[str, str | None]) -> dict:
    """One of a fixed set ``{name: what it means}``; the answer carries the
    full distribution and the most likely ``choice``."""
    if not 2 <= len(options) <= len(_CHOICE_LABELS):
        raise ValueError(f"a choice needs 2 to {len(_CHOICE_LABELS)} options")
    return {"type": "choice", "instructions": instructions, "options": dict(options)}


def question_text(question: Mapping[str, Any]) -> str:
    """A yes/no question with its criteria folded in (for backends that take
    only text)."""
    text = str(question["instructions"]).strip()
    if question.get("true"):
        text += f" Answer yes if: {question['true']}"
    if question.get("false"):
        text += f" Answer no if: {question['false']}"
    return text


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DecisionResult:
    """One answered call."""

    backend: str
    #: Names the thing that answered, revision included where the server gives
    #: one — it goes into reuse fingerprints.
    model: str
    answers: Mapping[str, dict]
    usage: Mapping[str, int] = field(default_factory=dict)
    latency_ms: float = 0.0

    def answers_as_dicts(self) -> dict[str, dict]:
        return {key: dict(value) for key, value in self.answers.items()}


class DecisionClient(Protocol):
    backend: str

    @property
    def model(self) -> str: ...

    def ask(
        self, state: Any, questions: Mapping[str, dict], *, model: str | None = None
    ) -> DecisionResult: ...


def _score_answer(probabilities: Sequence[float]) -> dict:
    total = sum(probabilities) or 1.0
    probs = [p / total for p in probabilities]
    return {
        "score": round(sum(i * p for i, p in enumerate(probs)), 6),
        "probabilities": {str(i): round(p, 6) for i, p in enumerate(probs)},
        "confidence": round(max(probs), 6),
    }


def _choice_answer(names: Sequence[str], probabilities: Sequence[float]) -> dict:
    total = sum(probabilities) or 1.0
    probs = [p / total for p in probabilities]
    best = max(range(len(names)), key=probs.__getitem__)
    return {
        "choice": names[best],
        "probabilities": {
            name: round(p, 6) for name, p in zip(names, probs, strict=True)
        },
        "confidence": round(probs[best], 6),
    }


# --------------------------------------------------------------------------- #
# Jev (hosted)
# --------------------------------------------------------------------------- #


class JevDecisionClient:
    """TypeSafe's Jev through :class:`apps.core.systemone.SystemOneClient`."""

    backend = JEV

    def __init__(self, inner: Any) -> None:
        self.inner = inner

    @property
    def model(self) -> str:
        return str(self.inner.config.model)

    def ask(
        self, state: Any, questions: Mapping[str, dict], *, model: str | None = None
    ) -> DecisionResult:
        from apps.core import systemone

        sdk_questions = {}
        for qid, q in questions.items():
            if q["type"] == "yesno":
                sdk_questions[qid] = systemone.noul(
                    q["instructions"], true=q.get("true"), false=q.get("false")
                )
            elif q["type"] == "score":
                sdk_questions[qid] = systemone.score(q["instructions"], q["levels"])
            else:
                sdk_questions[qid] = systemone.choice(q["instructions"], q["options"])
        started = time.perf_counter()
        result = self.inner.ask(state, sdk_questions, model=model)
        return DecisionResult(
            backend=JEV,
            model=result.model,
            answers=result.answers_as_dicts(),
            usage=dict(result.usage),
            latency_ms=(time.perf_counter() - started) * 1000,
        )


# --------------------------------------------------------------------------- #
# A port (decide or OpenAI-compatible)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PortConfig:
    url: str
    protocol: str = PROTOCOL_AUTO
    model: str = ""
    api_key: str = ""
    timeout: float = 30.0
    max_in_flight: int = 8

    @classmethod
    def from_settings(cls, settings: Any) -> PortConfig:
        protocol = str(
            _setting(settings, "DECISION_PORT_PROTOCOL", PROTOCOL_AUTO) or ""
        )
        return cls(
            url=base_url(str(_setting(settings, "DECISION_PORT_URL", ""))),
            protocol=protocol.strip().lower() or PROTOCOL_AUTO,
            model=str(_setting(settings, "DECISION_PORT_MODEL", "") or "").strip(),
            api_key=str(_setting(settings, "DECISION_PORT_API_KEY", "") or ""),
            timeout=float(_setting(settings, "DECISION_PORT_TIMEOUT", 30) or 30),
            max_in_flight=max(
                1, int(_setting(settings, "DECISION_PORT_MAX_IN_FLIGHT", 8) or 8)
            ),
        )


#: One gate per (server, limit), shared by every client in the process: the
#: reranker runs themes in parallel, each with its own thread pool, so a
#: per-client limit would still multiply (EXP-2026-11-014: the server ran out
#: of GPU memory at 32 production-length requests in flight).
_GATES: dict[tuple[str, int], threading.BoundedSemaphore] = {}
_GATES_LOCK = threading.Lock()


def _gate(url: str, limit: int) -> threading.BoundedSemaphore:
    with _GATES_LOCK:
        gate = _GATES.get((url, limit))
        if gate is None:
            gate = _GATES[(url, limit)] = threading.BoundedSemaphore(limit)
        return gate


def base_url(url: str) -> str:
    """``http://host:8080``, ``…/``, ``…/v1`` all mean the same server."""
    url = url.strip().rstrip("/")
    return url[: -len("/v1")] if url.endswith("/v1") else url


class _Http:
    """The two verbs a port client needs; replaceable in tests."""

    def __init__(self, config: PortConfig) -> None:
        self.config = config

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if self.config.api_key:
            headers["authorization"] = f"Bearer {self.config.api_key}"
        return headers

    def get(self, path: str) -> Any:
        import requests

        resp = requests.get(
            self.config.url + path, headers=self._headers(), timeout=self.config.timeout
        )
        return _json_or_raise(resp)

    def post(self, path: str, body: Mapping[str, Any]) -> Any:
        import requests

        resp = requests.post(
            self.config.url + path,
            data=json.dumps(body),
            headers=self._headers(),
            timeout=self.config.timeout,
        )
        return _json_or_raise(resp)


def _json_or_raise(resp: Any) -> Any:
    if resp.status_code >= 400:
        raise DecisionError(
            f"HTTP {resp.status_code} from {resp.url}: {resp.text[:300]}"
        )
    try:
        return resp.json()
    except ValueError as exc:
        raise DecisionError(f"non-JSON answer from {resp.url}") from exc


class PortDecisionClient:
    """A decision model the operator serves, reached by URL alone."""

    backend = PORT

    def __init__(self, config: PortConfig, *, http: Any | None = None) -> None:
        if not config.url:
            raise DecisionError("no port URL; set [decision] port_url")
        if config.protocol not in PROTOCOLS:
            raise DecisionError(
                f"[decision] port_protocol {config.protocol!r} is not one of "
                f"{PROTOCOLS}"
            )
        self.config = config
        self.http = http or _Http(config)
        self._gate = _gate(config.url, config.max_in_flight)
        self._lock = threading.Lock()
        self._protocol: str | None = (
            None if config.protocol == PROTOCOL_AUTO else config.protocol
        )
        self._model: str | None = None
        self._model_id: str | None = None

    # -- discovery ---------------------------------------------------------

    def _discover(self) -> None:
        """Read ``/v1/models`` once: the protocol and the model's full name."""
        with self._lock:
            if self._model_id is not None:
                return
            listing = self.http.get("/v1/models")
            if not isinstance(listing, Mapping):
                raise DecisionError("GET /v1/models did not return an object")
            protocol = self._protocol or (
                PROTOCOL_DECIDE if "question_types" in listing else PROTOCOL_OPENAI
            )
            if protocol == PROTOCOL_DECIDE:
                model, model_id = _decide_model(
                    listing.get("models") or [], self.config.model
                )
            else:
                model, model_id = _openai_model(
                    listing.get("data") or [], self.config.model
                )
            self._protocol, self._model, self._model_id = protocol, model, model_id

    @property
    def protocol(self) -> str:
        self._discover()
        return str(self._protocol)

    @property
    def model(self) -> str:
        """``<protocol>:<model>[@<revision>]`` — what the fingerprint names."""
        self._discover()
        return str(self._model_id)

    # -- asking ------------------------------------------------------------

    def ask(
        self, state: Any, questions: Mapping[str, dict], *, model: str | None = None
    ) -> DecisionResult:
        if not questions:
            raise DecisionError("no questions given")
        self._discover()
        with self._gate:
            started = time.perf_counter()
            if self._protocol == PROTOCOL_DECIDE:
                answers, usage, model_id = self._ask_decide(state, questions)
            else:
                answers, usage, model_id = self._ask_openai(state, questions)
        return DecisionResult(
            backend=PORT,
            model=model_id,
            answers=answers,
            usage=usage,
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    def _ask_decide(self, state, questions):
        wire = []
        for qid, q in questions.items():
            item: dict[str, Any] = {"id": qid, "type": q["type"]}
            if q["type"] == "yesno":
                item["question"] = question_text(q)
            elif q["type"] == "score":
                item["question"] = q["instructions"]
                item["scale"] = list(q["levels"])
            else:
                item["question"] = q["instructions"]
                item["options"] = dict(q["options"])
            wire.append(item)
        body: dict[str, Any] = {"input": state, "questions": wire}
        if self._model:
            body["model"] = self._model
        raw = self.http.post("/v1/decide", body)
        got = raw.get("answers") if isinstance(raw, Mapping) else None
        if not isinstance(got, Mapping):
            raise DecisionError("decide answer carried no answers")
        answers: dict[str, dict] = {}
        for qid, q in questions.items():
            a = got.get(qid)
            if not isinstance(a, Mapping) or "error" in a or "probs" not in a:
                message = a.get("message") if isinstance(a, Mapping) else "missing"
                raise DecisionError(f"decide could not answer {qid!r}: {message}")
            probs = a["probs"]
            if q["type"] == "yesno":
                answers[qid] = {"noul": round(float(probs["yes"]), 6)}
            elif q["type"] == "score":
                answers[qid] = _score_answer(_by_name(probs, q["levels"]))
            else:
                names = list(q["options"])
                answers[qid] = _choice_answer(names, _by_name(probs, names))
        model_id = self._model_id
        if raw.get("model"):
            model_id = f"decide:{raw['model']}" + (
                f"@{raw['revision']}" if raw.get("revision") else ""
            )
        return answers, {"input_tokens": 0, "output_tokens": 0}, model_id

    def _ask_openai(self, state, questions):
        answers: dict[str, dict] = {}
        usage = {"input_tokens": 0, "output_tokens": 0}
        context = json.dumps(state, ensure_ascii=False, default=str, sort_keys=True)
        for qid, q in questions.items():
            prompt, labels = _openai_prompt(q)
            raw = self.http.post(
                "/v1/chat/completions",
                {
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": _OPENAI_SYSTEM},
                        {"role": "user", "content": f"Input:\n{context}\n\n{prompt}"},
                    ],
                    "max_tokens": 1,
                    "temperature": 0,
                    "logprobs": True,
                    "top_logprobs": _TOP_LOGPROBS,
                    # Qwen-style templates (vLLM, llama.cpp): answer, don't think.
                    "chat_template_kwargs": {"enable_thinking": False},
                },
            )
            probs = _label_probabilities(raw, labels, case_fold=q["type"] == "yesno")
            if q["type"] == "yesno":
                answers[qid] = {"noul": round(probs[0], 6)}
            elif q["type"] == "score":
                answers[qid] = _score_answer(probs)
            else:
                answers[qid] = _choice_answer(list(q["options"]), probs)
            got = raw.get("usage") or {}
            usage["input_tokens"] += int(got.get("prompt_tokens") or 0)
            usage["output_tokens"] += int(got.get("completion_tokens") or 0)
        return answers, usage, self._model_id


def _by_name(probs: Mapping[str, float], names: Sequence[str]) -> list[float]:
    """Probabilities in ``names`` order, falling back to the server's order."""
    if all(name in probs for name in names):
        return [float(probs[name]) for name in names]
    values = [float(v) for v in probs.values()]
    if len(values) != len(names):
        raise DecisionError("decide answer has the wrong number of probabilities")
    return values


def _decide_model(models: Sequence[Mapping], wanted: str) -> tuple[str, str]:
    pick = None
    for m in models:
        if wanted and m.get("id") == wanted.split("@")[0]:
            pick = m
            break
    if pick is None and not wanted:
        pick = next((m for m in models if m.get("default")), None) or (
            models[0] if models else None
        )
    if pick is None:
        raise DecisionError(f"the decide server does not list a model {wanted!r}")
    model = str(pick["id"])
    revision = pick.get("revision")
    return model, f"decide:{model}" + (f"@{revision}" if revision else "")


def _openai_model(models: Sequence[Mapping], wanted: str) -> tuple[str, str]:
    if wanted:
        return wanted, f"openai:{wanted}"
    if not models:
        raise DecisionError("the server lists no models; set [decision] port_model")
    model = str(models[0].get("id"))
    return model, f"openai:{model}"


_OPENAI_SYSTEM = (
    "You make decisions about the JSON input the user gives you. Read the input, "
    "then reply with exactly one of the allowed answers and nothing else."
)


def _openai_prompt(q: Mapping[str, Any]) -> tuple[str, list[str]]:
    if q["type"] == "yesno":
        return f"Question: {question_text(q)}\nAllowed answers: yes, no", ["yes", "no"]
    if q["type"] == "score":
        labels = [str(i) for i in range(len(q["levels"]))]
        lines = "\n".join(f"{i}: {level}" for i, level in enumerate(q["levels"]))
        return (
            f"Question: {q['instructions']}\nLevels, lowest first:\n{lines}\n"
            f"Allowed answers: {', '.join(labels)} (the level's number)",
            labels,
        )
    names = list(q["options"])
    labels = list(_CHOICE_LABELS[: len(names)])
    lines = "\n".join(
        f"{label}: {name}" + (f" — {q['options'][name]}" if q["options"][name] else "")
        for label, name in zip(labels, names, strict=True)
    )
    return (
        f"Question: {q['instructions']}\nOptions:\n{lines}\n"
        f"Allowed answers: {', '.join(labels)} (the option's letter)",
        labels,
    )


def _label_probabilities(
    raw: Any, labels: Sequence[str], *, case_fold: bool
) -> list[float]:
    """Softmax of the allowed labels' first-token log-probabilities.

    Spellings of the same label (``Yes``, `` yes``) are summed. A label absent
    from the top-k gets nothing; when none appears the call is a failure.
    """
    try:
        first = raw["choices"][0]["logprobs"]["content"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise DecisionError(
            "no logprobs in the completion; the server must support "
            "logprobs/top_logprobs on /v1/chat/completions"
        ) from exc
    candidates = list(first.get("top_logprobs") or []) or [first]
    mass = dict.fromkeys(labels, 0.0)
    for entry in candidates:
        token = str(entry.get("token", "")).strip().strip(".:,)").strip()
        key = token.lower() if case_fold else token
        if key in mass:
            mass[key] += math.exp(float(entry.get("logprob", -math.inf)))
    total = sum(mass.values())
    if total <= 0:
        raise DecisionError(f"none of {list(labels)} among the top answer tokens")
    return [mass[label] / total for label in labels]


# --------------------------------------------------------------------------- #
# The ledger wrapper and the factory
# --------------------------------------------------------------------------- #


class _Counted:
    """Counts every call in the LLM ledger; never changes what the caller sees."""

    def __init__(self, inner: Any, component: str) -> None:
        self.inner = inner
        self.backend = inner.backend
        self.component = component

    @property
    def model(self) -> str:
        return self.inner.model

    def ask(self, state, questions, *, model=None) -> DecisionResult:
        try:
            result = self.inner.ask(state, questions, model=model)
        except Exception:
            if self.backend != JEV:  # SystemOneClient already counted it
                llm_usage.record(self.component, ok=False)
            raise
        if self.backend != JEV:
            llm_usage.record(self.component, ok=True, usage=result.usage)
        return result


def build_decision_client(
    settings: Any | None = None,
    *,
    backend: str | None = None,
    component: str = "",
    http: Any | None = None,
) -> DecisionClient | None:
    """The client for the resolved backend, or ``None`` when it is ``off``.

    ``backend`` overrides the configured one (``jev`` / ``port``); it is
    resolved the same way, so an override missing its key or URL is ``None``.
    """
    settings = _django(settings)
    if backend is not None:
        chosen = normalise(backend)

        class _Override:
            def __getattr__(self, name):
                if name == "DECISION_BACKEND":
                    return chosen
                return getattr(settings, name)

        resolved, _reason = resolve(_Override())
    else:
        resolved, _reason = resolve(settings)
    if resolved == JEV:
        from apps.core.systemone import build_systemone_client

        inner: Any = JevDecisionClient(
            build_systemone_client(settings, component=component)
        )
    elif resolved == PORT:
        inner = PortDecisionClient(PortConfig.from_settings(settings), http=http)
    else:
        return None
    return _Counted(inner, component or f"decision.{resolved}")
