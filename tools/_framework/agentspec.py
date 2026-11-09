"""The vocabulary a tool uses to give the Mylo agent functions and references.

Standard library only, like ``spec.py``: a tool contributes to the agent by
declaring ``agent = "tools.<name>.agent"`` in its ``tool.py`` and exporting
``FUNCTIONS`` and ``REFS`` from that module, written in the classes below. It
never imports the agent tool, so the agent can be disabled or deleted and the
contributing tool still loads (and the agent never depends on it either).

The permission fields (``risk``, ``output``, ``scopes``, ``min_role``) have no
defaults on purpose: the agent's declaration test fails a function that leaves
one out. See docs/plans/mylo-agent/permissions.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: What a function may do. Only ``read`` loads in this pass.
RISKS = ("read", "write", "external", "destructive")
#: Visibility widths, narrowest first. A function may run only when its
#: ``output`` is at least as wide as the audience of the reply.
WIDTHS = ("person", "project", "lab", "department", "instance")
#: Thread scopes.
SCOPES = ("personal", "lab", "department", "project")
#: Roles per scope kind, lowest first.
ROLES = {
    "lab": ("viewer", "member", "admin", "owner"),
    "department": ("viewer", "member", "admin", "owner"),
    "project": ("viewer", "editor"),
}
SURFACES = ("web", "discord", "cli", "token")


def width_rank(width: str) -> int:
    return WIDTHS.index(width)


@dataclass(frozen=True)
class AgentFunction:
    """One function the model can call.

    ``handler`` is ``"package.module:function"`` taking ``(caller, **args)``
    and returning a :class:`Result`. Object arguments carry ``"x-ref": kind``
    in ``parameters`` so the gate clears each one before the handler runs.
    """

    name: str
    summary: str
    description: str
    parameters: dict
    handler: str
    risk: str
    output: str
    scopes: tuple
    min_role: dict
    surfaces: tuple = ("web", "discord", "cli")
    #: A ``features.*`` key (``"features.collab_search"``) and/or an
    #: entitlement feature (``"entitlement:agent_files"``) that must be on.
    feature: str | None = None
    core: bool = False
    examples: tuple = ()
    confirm: tuple = ()
    #: Also write an AuditEvent (reading another person's data).
    audit: bool = False
    #: The group it is listed and switched off under. Defaults to the part of
    #: the name before the first underscore (``corpus_search`` → ``corpus``).
    group: str = ""

    def __post_init__(self) -> None:
        if not self.group:
            object.__setattr__(self, "group", self.name.split("_", 1)[0])

    def schema(self) -> dict:
        """The OpenAI ``tools=`` entry, with the private ``x-ref`` marks removed."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": _strip_private(self.parameters),
            },
        }

    def ref_args(self) -> dict[str, str]:
        """``{argument: ref kind}`` for every ``x-ref`` property (top level,
        or the items of an array property)."""
        out: dict[str, str] = {}
        for key, prop in (self.parameters.get("properties") or {}).items():
            kind = prop.get("x-ref") or (prop.get("items") or {}).get("x-ref")
            if kind:
                out[key] = kind
        return out


def _strip_private(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: _strip_private(v) for k, v in value.items() if not k.startswith("x-")
        }
    if isinstance(value, list):
        return [_strip_private(v) for v in value]
    return value


@dataclass(frozen=True)
class RefInfo:
    """A resolved, visible object: what the thread numbers ``#n``."""

    kind: str
    key: str
    title: str
    #: One or two lines for the card the model and the person see.
    card: str = ""
    #: The widest audience this object may be shown to.
    output: str = "person"
    #: How the model reads more ("fulltext_read_paper(ref='#3')").
    read_with: str = ""
    #: Text that came from outside (a paper, a grant, a file): wrapped as
    #: untrusted wherever the model reads it.
    untrusted: bool = False

    @property
    def ref(self) -> str:
        return f"{self.kind}:{self.key}"


@dataclass(frozen=True)
class RefKind:
    """A kind of object people can tag with ``@`` and functions can take.

    ``resolve`` is ``"module:function"`` taking ``(caller, key)`` and returning
    a :class:`RefInfo`, or ``None`` when the object does not exist **or** the
    caller may not see it — the two are never told apart. ``search`` (optional)
    takes ``(caller, query, limit)`` and returns ``RefInfo``s for the @ picker.
    """

    kind: str
    resolve: str
    search: str | None = None
    summary: str = ""


@dataclass
class Result:
    """What a handler returns.

    ``content`` is what the model reads. ``refs`` are the objects it surfaced;
    the agent numbers them ``#n`` in the thread. ``untrusted`` marks content
    that came from outside (paper text, file text), which the agent wraps.
    """

    content: str
    data: Any = None
    refs: list[RefInfo] = field(default_factory=list)
    untrusted: bool = False


class FunctionError(Exception):
    """A handler's refusal or failure, in a shape the model can act on."""

    def __init__(self, code: str, detail: str, fix: str = "") -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.fix = fix

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail, "fix": self.fix}
