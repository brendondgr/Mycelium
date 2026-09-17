"""TypeSafe System One client for Mycelium — typed decisions, not text.

The OpenAI-compatible client in :mod:`apps.core.llm` generates prose. This is
the other kind of model call: a *decision*. TypeSafe's Jev takes a piece of
state plus a map of typed questions and returns typed answers — a probability
for a yes/no, a distribution over options, a probability-weighted position on
an ordered scale — each with a confidence. It cannot write a sentence, so it
can never replace the prose path; it is a sidecar for the judgements inside it
(a verdict, an eligibility, a relevance) that today come out of a JSON blob a
language model was asked to emit.

**Prototype seam.** Nothing in production calls this. The first consumers are
the research record (``docs/research/experiments/EXP-2026-09-003-…``) and the
eval harness. Keep it that way until an experiment says otherwise.

Three design choices mirror :mod:`apps.core.llm` on purpose:

* **Lazy import.** ``typesafe_sdk`` is imported only when a real transport is
  built, so importing this module costs nothing and needs no key.
* **Injectable transport.** :class:`SystemOneClient` takes any object with the
  SDK's ``system_one`` method; tests pass a fake and run offline.
* **The ledger observes, never intervenes.** Every call is counted in
  :mod:`apps.core.llm_usage` under the caller's ``component`` label, on success
  and on failure, and recording can never change what the caller sees.

One choice is deliberately different: the model is **pinned to a version**
(``jev-1.13.0``), never the ``jev-latest`` alias, because a number in the record
has to name the thing that produced it. :func:`is_pinned` is the check.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from apps.core import llm_usage

DEFAULT_MODEL = "jev-1.13.0"
DEFAULT_BASE_URL = "https://api.typesafe.ai"

#: The aliases the API accepts and this seam refuses to record a number under.
ALIASES: frozenset[str] = frozenset({"jev-latest", "jev-preview"})


class SystemOneConfigurationError(RuntimeError):
    """Raised before any network call when the client cannot be built."""


def is_pinned(model: str | None) -> bool:
    """Whether ``model`` names a version rather than a moving alias."""
    return bool(model) and str(model).strip().lower() not in ALIASES


@dataclass(frozen=True)
class SystemOneConfig:
    """Everything needed to reach the endpoint."""

    api_key: str = ""
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    timeout: float = 10.0
    # Retries belong to the caller, as with ``LLMConfig.max_retries``: a caller
    # with a deterministic fallback should reach it, not wait through backoff.
    max_retries: int = 0

    @classmethod
    def from_settings(cls, settings: Any) -> SystemOneConfig:
        """Build config from Django settings (the ``TYPESAFE_*`` group)."""
        return cls(
            api_key=str(getattr(settings, "TYPESAFE_API_KEY", "") or ""),
            model=str(
                getattr(settings, "TYPESAFE_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL
            ),
            base_url=str(
                getattr(settings, "TYPESAFE_BASE_URL", DEFAULT_BASE_URL)
                or DEFAULT_BASE_URL
            ),
            timeout=float(getattr(settings, "TYPESAFE_TIMEOUT", 10.0)),
            max_retries=int(getattr(settings, "TYPESAFE_MAX_RETRIES", 0)),
        )


class SystemOneTransport(Protocol):
    """The slice of ``typesafe_sdk.TypeSafeClient`` this client uses."""

    def system_one(
        self, state: Any, questions: Mapping[str, Any], *, model: str | None = None
    ) -> Any: ...


@dataclass(frozen=True)
class SystemOneResult:
    """One answered call, with the accounting the record needs."""

    model: str
    #: The SDK's answer objects keyed by question id (``.noul``, ``.score``,
    #: ``.choice``, ``.probabilities``, ``.confidence`` as each type carries).
    answers: Mapping[str, Any]
    #: ``{"input_tokens": int, "output_tokens": int}`` — the spellings the
    #: ledger reads; ``None`` from the API becomes 0.
    usage: Mapping[str, int]
    request_id: str | None
    raw: Any = None

    def answers_as_dicts(self) -> dict[str, dict[str, Any]]:
        """Plain-JSON answers, for dumping next to a run."""
        return {key: answer_to_dict(value) for key, value in self.answers.items()}


def answer_to_dict(answer: Any) -> dict[str, Any]:
    """Flatten one SDK answer (or a look-alike) into JSON-safe fields."""
    out: dict[str, Any] = {}
    for name in ("noul", "choice", "score", "confidence"):
        value = getattr(answer, name, None)
        if value is not None:
            out[name] = value
    probabilities = getattr(answer, "probabilities", None)
    if isinstance(probabilities, Mapping):
        out["probabilities"] = {str(k): float(v) for k, v in probabilities.items()}
    legend = getattr(answer, "legend", None)
    if isinstance(legend, Mapping):
        out["legend"] = {str(k): v for k, v in legend.items()}
    return out


def _usage_dict(usage: Any) -> dict[str, int]:
    def _int(name: str) -> int:
        value = getattr(usage, name, None) if usage is not None else None
        if value is None and isinstance(usage, Mapping):
            value = usage.get(name)
        return max(0, int(value)) if isinstance(value, (int, float)) else 0

    return {
        "input_tokens": _int("input_tokens"),
        "output_tokens": _int("output_tokens"),
    }


class SystemOneClient:
    """Ask typed questions of a piece of state. See the module docstring."""

    def __init__(
        self,
        config: SystemOneConfig,
        *,
        transport: SystemOneTransport | None = None,
        component: str = "",
    ) -> None:
        self.config = config
        self._transport = transport
        self.component = component

    @classmethod
    def from_settings(
        cls,
        settings: Any,
        *,
        transport: SystemOneTransport | None = None,
        component: str = "",
    ) -> SystemOneClient:
        return cls(
            SystemOneConfig.from_settings(settings),
            transport=transport,
            component=component,
        )

    @property
    def transport(self) -> SystemOneTransport:
        """The SDK client, built lazily on first use."""
        if self._transport is None:
            self._transport = self._build_transport()
        return self._transport

    def _build_transport(self) -> SystemOneTransport:
        if not self.config.api_key:
            raise SystemOneConfigurationError(
                "TYPESAFE_API_KEY is not set; put it in the repository root .env"
            )
        from typesafe_sdk import (  # lazy: no SDK needed to import
            RetryPolicy,
            TypeSafeClient,
        )

        return TypeSafeClient(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            model=self.config.model,
            timeout=self.config.timeout,
            retry=RetryPolicy(max_retries=max(0, self.config.max_retries)),
        )

    def ask(
        self,
        state: Any,
        questions: Mapping[str, Any],
        *,
        model: str | None = None,
    ) -> SystemOneResult:
        """Evaluate ``questions`` against ``state`` in one call.

        Every question is answered in parallel against the same state, so the
        marginal question is close to free; batch them. The call is counted in
        the ledger either way and the original exception is re-raised untouched.
        """
        if not questions:
            raise SystemOneConfigurationError("no questions given")
        resolved_model = model or self.config.model
        if not resolved_model:
            raise SystemOneConfigurationError("no model configured; set TYPESAFE_MODEL")

        try:
            raw = self.transport.system_one(state, questions, model=resolved_model)
            result = self._parse(raw, fallback_model=resolved_model)
        except Exception:
            llm_usage.record(self.component, ok=False)
            raise
        llm_usage.record(self.component, ok=True, usage=result.usage)
        return result

    @staticmethod
    def _parse(raw: Any, *, fallback_model: str) -> SystemOneResult:
        answers = getattr(raw, "answers", None)
        if not isinstance(answers, Mapping):
            raise SystemOneConfigurationError("System One response carried no answers")
        return SystemOneResult(
            model=str(getattr(raw, "model", "") or fallback_model),
            answers=dict(answers),
            usage=_usage_dict(getattr(raw, "usage", None)),
            request_id=getattr(raw, "request_id", None),
            raw=raw,
        )


# --------------------------------------------------------------------------- #
# Question constructors — so a caller never imports the SDK just to ask.
# --------------------------------------------------------------------------- #


def noul(instructions: Any, *, true: Any = None, false: Any = None) -> Any:
    """A yes/no question; the answer is a probability in [0, 1]."""
    from typesafe_sdk import Noul, NoulCriteria

    criteria = NoulCriteria(true=true, false=false) if (true or false) else None
    return Noul(instructions=instructions, criteria=criteria)


def score(instructions: Any, levels: Any) -> Any:
    """An ordered scale. ``levels`` run low to high, 2 to 10 of them, each a
    concrete description rather than a degree word. The answer's ``score`` is
    the probability-weighted level index."""
    from typesafe_sdk import Score

    return Score(instructions=instructions, criteria=list(levels))


def choice(instructions: Any, options: Mapping[str, Any]) -> Any:
    """One of a fixed set; the answer carries the full distribution."""
    from typesafe_sdk import Choice

    return Choice(instructions=instructions, criteria=dict(options))


def build_systemone_client(
    settings: Any | None = None,
    *,
    transport: SystemOneTransport | None = None,
    component: str = "",
) -> SystemOneClient:
    """Convenience factory. Defaults to Django settings when none are given.

    Pass ``component`` so the calls show up under a meaningful name in the daily
    LLM ledger; unlabelled clients are counted as ``unlabelled``.
    """
    if settings is None:
        from django.conf import settings as django_settings

        settings = django_settings
    return SystemOneClient.from_settings(
        settings, transport=transport, component=component
    )
