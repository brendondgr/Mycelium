#!/usr/bin/env python3
"""``mycelium config`` — read, explain, change and check ``mycelium.toml``.

Usage (from the repo root; ``make config ARGS="..."`` and ``ops/mycelium config``
run the same thing):

    config profiles                      the four deployment profiles
    config init [--profile lab]          write mycelium.toml for a profile
    config show [--changed]              every value in effect and where it came from
    config explain [KEY | SECTION]       what a key does, its choices, per-profile values
    config get KEY                       one value
    config set KEY VALUE [KEY VALUE...]  change values in mycelium.toml (validated first)
    config unset KEY                     drop a key so the profile's value applies
    config validate                      check the combination works; exit 1 if not
    config diff                          what mycelium.toml changes from its profile
    config recommend [--people N] ...    suggest a profile and settings, with reasons

Every command takes ``--json`` for agents. Values are read exactly as the backend
reads them: defaults → profile → mycelium.toml → environment (this shell plus
``.env``). The definitions live in ``web/backend/config/instance.py``; this file
only presents them, so the CLI and the server can never disagree.

Standard library only: it runs on the host with any Python 3.11+, before the
stack (or ``uv``) exists.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DOTENV = ROOT / ".env"


def _load_instance():
    path = ROOT / "web" / "backend" / "config" / "instance.py"
    spec = importlib.util.spec_from_file_location("mycelium_instance", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations through it
    spec.loader.exec_module(module)
    return module


inst = _load_instance()
# The same file the backend reads (``MYCELIUM_CONFIG`` points elsewhere).
CONFIG = inst.config_path(ROOT, os.environ) or ROOT / inst.CONFIG_FILENAME

_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def bold(t: str) -> str: return _c("1", t)
def dim(t: str) -> str: return _c("2", t)
def green(t: str) -> str: return _c("32", t)
def red(t: str) -> str: return _c("31", t)
def yellow(t: str) -> str: return _c("33", t)


# --------------------------------------------------------------------------- #
# Environment and values
# --------------------------------------------------------------------------- #


def read_dotenv(path: Path = DOTENV) -> dict[str, str]:
    """``KEY=value`` lines of ``.env``, the way Compose reads them (no expansion)."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def environment() -> dict[str, str]:
    """What the containers see: ``.env``, overridden by this shell."""
    return {**read_dotenv(), **os.environ}


def resolve(file_values: dict | None = None):
    return inst.resolve(ROOT, environment(), file_values=file_values)


def shown(value: Any) -> str:
    if value is inst.UNLIMITED:
        return "unlimited"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(value) + "]" if value else "[]"
    return str(value)


def jsonable(value: Any) -> Any:
    return "unlimited" if value is inst.UNLIMITED else value


def parse_cli_value(key: str, raw: str) -> Any:
    """A command-line string as the TOML value it should be written as."""
    setting = inst.BY_KEY[key]
    value = inst._coerce(setting, raw, "the command line")
    return value


def emit(data: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=False))


def die(message: str, as_json: bool, code: int = 1) -> int:
    if as_json:
        print(json.dumps({"ok": False, "error": message}, indent=2))
    else:
        print(red(f"✗ {message}"), file=sys.stderr)
    return code


def known_key(key: str) -> bool:
    return key in inst.BY_KEY


def matching_keys(prefix: str) -> list[str]:
    prefix = prefix.rstrip(".")
    return [k for k in inst.BY_KEY if k == prefix or k.startswith(prefix + ".")]


# --------------------------------------------------------------------------- #
# Editing mycelium.toml in place (comments preserved)
# --------------------------------------------------------------------------- #

_HEADER = re.compile(r"^\s*\[([^\[\]]+)\]\s*(#.*)?$")


def _split_value_comment(rest: str) -> tuple[str, str]:
    """Split ``value  # comment`` without breaking a '#' inside a string."""
    in_string, quote = False, ""
    for index, char in enumerate(rest):
        if char in "\"'" and (not in_string or char == quote):
            in_string, quote = (not in_string), char
        elif char == "#" and not in_string:
            return rest[:index].rstrip(), rest[index:]
    return rest.rstrip(), ""


def edit_file(text: str, changes: dict[str, Any], removals: set[str]) -> str:
    """Return ``text`` with ``changes`` written and ``removals`` dropped.

    An existing ``name = value`` line keeps its indentation and trailing comment;
    a key the file lacks is appended to its section (created if missing).
    """
    lines = text.splitlines()
    section = ""
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        header = _HEADER.match(line)
        if header:
            section = header.group(1).strip()
            out.append(line)
            continue
        match = re.match(r"^(\s*)([A-Za-z0-9_\-]+)(\s*=\s*)(.*)$", line)
        if match and not line.lstrip().startswith("#"):
            key = f"{section}.{match.group(2)}" if section else match.group(2)
            if key in removals:
                seen.add(key)
                continue
            if key in changes:
                value, comment = _split_value_comment(match.group(4))
                new = f"{match.group(1)}{match.group(2)}{match.group(3)}"
                new += inst._toml_value(changes[key])
                if comment:
                    new = f"{new:<40} {comment}"
                out.append(new)
                seen.add(key)
                continue
        out.append(line)

    missing = [k for k in changes if k not in seen]
    for key in missing:
        sec, _, name = key.rpartition(".")
        assignment = f"{name} = {inst._toml_value(changes[key])}"
        # Find the section and append at its end; else add the section.
        start = None
        for index, line in enumerate(out):
            header = _HEADER.match(line)
            if header and header.group(1).strip() == sec:
                start = index
                break
        if start is None:
            if out and out[-1].strip():
                out.append("")
            out.extend([f"[{sec}]", assignment])
            continue
        end = start + 1
        while end < len(out) and not _HEADER.match(out[end]):
            end += 1
        while end > start + 1 and not out[end - 1].strip():
            end -= 1
        out.insert(end, assignment)
    return "\n".join(out) + "\n"


def file_values_after(changes: dict[str, Any], removals: set[str]) -> dict[str, Any]:
    current = inst.read_file(CONFIG) if CONFIG.is_file() else {}
    merged = {k: v for k, v in current.items() if k not in removals}
    for key, value in changes.items():
        merged[key] = "unlimited" if value is inst.UNLIMITED else value
    return merged


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


def cmd_profiles(args) -> int:
    rows = [
        {"name": name, "description": inst.PROFILE_HELP[name],
         "sets": {k: jsonable(v) for k, v in inst.PROFILES[name].items()},
         "default": name == inst.DEFAULT_PROFILE}
        for name in inst.PROFILE_NAMES
    ]
    if args.json:
        emit(rows, True)
        return 0
    for row in rows:
        mark = " (default)" if row["default"] else ""
        print(f"{bold(row['name'])}{mark}  {row['description']}")
        for key, value in row["sets"].items():
            print(dim(f"    {key} = {shown(value if value != 'unlimited' else None)}"))
    return 0


def cmd_init(args) -> int:
    target = Path(args.output) if args.output else CONFIG
    if target.exists() and not args.force:
        return die(
            f"{target.name} already exists. Use `config set` to change it, or "
            "--force to overwrite it.", args.json,
        )
    overrides = {}
    for pair in args.set or []:
        key, _, raw = pair.partition("=")
        if not known_key(key):
            return die(f"Unknown key {key!r}.", args.json)
        try:
            overrides[key] = parse_cli_value(key, raw)
        except inst.ConfigError as exc:
            return die(str(exc), args.json)
    try:
        text = inst.render(args.profile, overrides)
    except inst.ConfigError as exc:
        return die(str(exc), args.json)
    target.write_text(text)
    cfg = resolve() if target == CONFIG else None
    problems = cfg.problems(environment()) if cfg else []
    if args.json:
        emit({"ok": True, "path": str(target), "profile": args.profile,
              "problems": problems}, True)
        return 0
    print(green(f"✓ wrote {target.relative_to(ROOT) if target.is_relative_to(ROOT) else target} "
                f"({args.profile} profile)"))
    for problem in problems:
        print(yellow(f"  ! {problem}"))
    print(dim("  Restart the stack (`make restart`) for the backend to read it."))
    return 0


def cmd_show(args) -> int:
    try:
        cfg = resolve()
    except inst.ConfigError as exc:
        return die(str(exc), args.json)
    keys = [k for k in inst.BY_KEY
            if not args.changed or cfg[k] != inst.BY_KEY[k].default]
    if args.json:
        emit({
            "profile": cfg.profile,
            "file": str(cfg.path) if cfg.path else None,
            "values": {k: {"value": jsonable(cfg[k]), "source": cfg.sources[k]}
                       for k in keys},
            "problems": cfg.problems(environment()),
        }, True)
        return 0
    where = cfg.path.name if cfg.path else "no mycelium.toml (profile defaults)"
    print(f"{bold('profile')} {cfg.profile}   {dim(where)}")
    section = None
    for key in keys:
        sec = inst.BY_KEY[key].section
        if sec != section:
            print(f"\n{bold('[' + sec + ']')}")
            section = sec
        source = cfg.sources[key]
        tag = dim(source) if source == "default" else yellow(source)
        print(f"  {inst.BY_KEY[key].name:<28} {shown(cfg[key]):<24} {tag}")
    problems = cfg.problems(environment())
    if problems:
        print()
        for problem in problems:
            print(yellow(f"! {problem}"))
    return 0


def _explain_one(key: str) -> dict:
    setting = inst.BY_KEY[key]
    by_profile = {
        name: jsonable(inst.PROFILES[name].get(key, setting.default))
        for name in inst.PROFILE_NAMES
    }
    if key == "instance.profile":
        by_profile = {name: name for name in inst.PROFILE_NAMES}
    return {
        "key": key, "type": setting.kind, "help": setting.help,
        "env": setting.env, "choices": list(setting.choices) or None,
        "default": jsonable(setting.default), "suggested": setting.suggested,
        "by_profile": by_profile,
    }


def cmd_explain(args) -> int:
    target = args.key or ""
    keys = matching_keys(target) if target else list(inst.BY_KEY)
    if not keys:
        return die(f"No key or section named {target!r}.", args.json)
    rows = [_explain_one(k) for k in keys]
    if args.json:
        emit(rows, True)
        return 0
    for row in rows:
        print(bold(row["key"]) + dim(f"  ({row['type']})"))
        print(f"  {row['help']}")
        if row["choices"]:
            print(dim(f"  choices: {' | '.join(row['choices'])}"))
        extras = []
        if row["env"]:
            extras.append(f"env {row['env']}")
        if row["suggested"] is not None:
            extras.append(f"suggested {row['suggested']}")
        if extras:
            print(dim("  " + "; ".join(extras)))
        profiles = ", ".join(f"{p}={shown(v if v != 'unlimited' else None)}"
                             for p, v in row["by_profile"].items())
        print(dim(f"  profiles: {profiles}"))
        print()
    return 0


def cmd_get(args) -> int:
    if not known_key(args.key):
        return die(f"Unknown key {args.key!r}. Try `config explain`.", args.json)
    try:
        cfg = resolve()
    except inst.ConfigError as exc:
        return die(str(exc), args.json)
    if args.json:
        emit({"key": args.key, "value": jsonable(cfg[args.key]),
              "source": cfg.sources[args.key]}, True)
    else:
        print(shown(cfg[args.key]))
    return 0


def _apply(changes: dict[str, Any], removals: set[str], args) -> int:
    if not CONFIG.is_file():
        return die("No mycelium.toml yet. Run `config init` first.", args.json)
    try:
        after = resolve(file_values_after(changes, removals))
    except inst.ConfigError as exc:
        return die(str(exc), args.json)
    CONFIG.write_text(edit_file(CONFIG.read_text(), changes, removals))
    env = environment()
    overridden = [
        f"{key} is overridden by env {inst.BY_KEY[key].env}"
        for key in list(changes) + sorted(removals)
        if after.sources[key].startswith("env:")
    ]
    problems = after.problems(env)
    if args.json:
        emit({"ok": True,
              "changed": {k: jsonable(after[k]) for k in list(changes) + sorted(removals)},
              "warnings": overridden, "problems": problems}, True)
        return 0
    for key in list(changes) + sorted(removals):
        print(green(f"✓ {key} = {shown(after[key])}") + dim(f"  ({after.sources[key]})"))
    for line in overridden:
        print(yellow(f"! {line}; the file value will not take effect"))
    for problem in problems:
        print(yellow(f"! {problem}"))
    print(dim("  Restart the stack (`make restart`) for the backend to read it."))
    return 0


def cmd_set(args) -> int:
    pairs = args.pairs
    if len(pairs) % 2:
        return die("`config set` takes KEY VALUE pairs.", args.json)
    changes: dict[str, Any] = {}
    for key, raw in zip(pairs[::2], pairs[1::2]):
        if not known_key(key):
            return die(f"Unknown key {key!r}. Try `config explain`.", args.json)
        if key == "instance.profile":
            raw = raw.strip().lower()
        try:
            changes[key] = parse_cli_value(key, raw)
        except inst.ConfigError as exc:
            return die(str(exc), args.json)
    return _apply(changes, set(), args)


def cmd_unset(args) -> int:
    for key in args.keys:
        if not known_key(key):
            return die(f"Unknown key {key!r}.", args.json)
    return _apply({}, set(args.keys), args)


def cmd_validate(args) -> int:
    try:
        cfg = resolve()
    except inst.ConfigError as exc:
        return die(str(exc), args.json)
    problems = cfg.problems(environment())
    if args.json:
        emit({"ok": not problems, "profile": cfg.profile, "problems": problems}, True)
    elif problems:
        for problem in problems:
            print(red(f"✗ {problem}"))
    else:
        print(green(f"✓ configuration is valid ({cfg.profile} profile)"))
    return 1 if problems else 0


def cmd_diff(args) -> int:
    try:
        cfg = resolve()
    except inst.ConfigError as exc:
        return die(str(exc), args.json)
    base = inst.resolve(ROOT, {}, file_values={"instance.profile": cfg.profile})
    rows = [
        {"key": k, "profile": jsonable(base[k]), "value": jsonable(cfg[k]),
         "source": cfg.sources[k]}
        for k in inst.BY_KEY
        if k != "instance.profile" and cfg[k] != base[k]
    ]
    if args.json:
        emit({"profile": cfg.profile, "differences": rows}, True)
        return 0
    if not rows:
        print(f"Nothing differs from the {cfg.profile} profile.")
        return 0
    print(f"Differences from the {bold(cfg.profile)} profile:")
    for row in rows:
        before = shown(None if row["profile"] == "unlimited" else row["profile"])
        after = shown(None if row["value"] == "unlimited" else row["value"])
        print(f"  {row['key']:<36} {dim(before)} → {after}  {dim(row['source'])}")
    return 0


def recommend(people: int | None, scope: str | None, email: str | None,
              paid_llm: bool, public: bool) -> dict:
    """A profile and a handful of overrides, each with the reason for it.

    Deterministic and deliberately simple: it is the starting point an agent
    proposes to its user, not a final answer.
    """
    reasons: list[str] = []
    if scope in inst.PROFILES:
        profile = scope
        reasons.append(f"You said this instance serves a {scope}.")
    elif people is None or people <= 1:
        profile = "personal"
        reasons.append("One person: no sign-up, no limits, no email needed.")
    elif people <= 40:
        profile = "lab"
        reasons.append(f"{people} people is one lab: invite-based, no limits.")
    elif people <= 300:
        profile = "department"
        reasons.append(f"{people} people spans several labs: the department profile.")
    else:
        profile = "institution"
        reasons.append(f"{people} people is a school-wide service: tier limits, "
                       "a sign-up code, verified email.")
    overrides: dict[str, Any] = {}
    if email in ("resend", "smtp"):
        overrides["email.provider"] = email
        reasons.append(f"Mail goes out through {email}; put its secret in .env.")
    elif email == "none" and inst.PROFILES[profile].get("email.provider"):
        overrides["email.provider"] = "none"
        overrides["signup.verify_email"] = False
        reasons.append("No mail server: verification is switched off so nobody "
                       "waits for a code that cannot arrive.")
        if inst.PROFILES[profile].get("signup.mode") == "domain":
            overrides["signup.mode"] = "invite"
    if public and profile in ("personal", "lab"):
        if profile == "personal":
            reasons.append("Reachable from the internet but closed to sign-up, "
                           "which is the safe default for one person.")
        else:
            reasons.append("Reachable from the internet: invites only, so a "
                           "stranger cannot register.")
    if paid_llm:
        size = max(people or 1, 1)
        budget = max(500, size * 150)
        overrides["nightly.model_calls"] = budget
        reasons.append(f"A paid model API: cap the nightly run at about {budget} "
                       "model calls (~150 per person); raise it once you have "
                       "seen a real night's usage.")
    if profile in ("department", "institution") and not paid_llm:
        reasons.append("Self-hosted model: no nightly call budget; the "
                       "concurrency keys bound the load instead.")
    return {"profile": profile, "set": {k: jsonable(v) for k, v in overrides.items()},
            "reasons": reasons}


def cmd_recommend(args) -> int:
    result = recommend(args.people, args.scope, args.email, args.paid_llm,
                       args.public)
    if args.apply:
        if CONFIG.exists() and not args.force:
            return die("mycelium.toml exists; add --force to replace it.", args.json)
        CONFIG.write_text(inst.render(
            result["profile"],
            {k: (None if v == "unlimited" else v) for k, v in result["set"].items()},
        ))
        result["written"] = str(CONFIG)
    if args.json:
        emit(result, True)
        return 0
    print(f"{bold('Recommended profile:')} {result['profile']}")
    for key, value in result["set"].items():
        print(f"  set {key} = {value}")
    for reason in result["reasons"]:
        print(dim(f"  · {reason}"))
    if args.apply:
        print(green("✓ wrote mycelium.toml"))
    else:
        flags = " ".join(f"--set {k}={v}" for k, v in result["set"].items())
        print(dim(f"\n  Apply: ops/mycelium config init --profile {result['profile']} {flags}".rstrip()))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mycelium config",
        description="Read, explain, change and check mycelium.toml.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, help_text: str):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--json", action="store_true", help="machine-readable output")
        return p

    add("profiles", "list the deployment profiles").set_defaults(fn=cmd_profiles)

    p = add("init", "write mycelium.toml for a profile")
    p.add_argument("--profile", default=os.environ.get("MYCELIUM_PROFILE")
                   or inst.DEFAULT_PROFILE, choices=inst.PROFILE_NAMES)
    p.add_argument("--set", action="append", metavar="KEY=VALUE",
                   help="override one key (repeatable)")
    p.add_argument("--output", help="write somewhere other than mycelium.toml")
    p.add_argument("--force", action="store_true", help="overwrite an existing file")
    p.set_defaults(fn=cmd_init)

    p = add("show", "every value in effect and where it came from")
    p.add_argument("--changed", action="store_true",
                   help="only values that differ from the built-in default")
    p.set_defaults(fn=cmd_show)

    p = add("explain", "what a key or section does")
    p.add_argument("key", nargs="?", help="a key (limits.clusters) or section (limits)")
    p.set_defaults(fn=cmd_explain)

    p = add("get", "print one value")
    p.add_argument("key")
    p.set_defaults(fn=cmd_get)

    p = add("set", "change values in mycelium.toml")
    p.add_argument("pairs", nargs="+", metavar="KEY VALUE")
    p.set_defaults(fn=cmd_set)

    p = add("unset", "drop keys so the profile's value applies")
    p.add_argument("keys", nargs="+")
    p.set_defaults(fn=cmd_unset)

    add("validate", "check the configuration works").set_defaults(fn=cmd_validate)
    add("diff", "what mycelium.toml changes from its profile").set_defaults(fn=cmd_diff)

    p = add("recommend", "suggest a profile and settings")
    p.add_argument("--people", type=int, help="how many people will use it")
    p.add_argument("--scope", choices=inst.PROFILE_NAMES,
                   help="who it serves, if you already know")
    p.add_argument("--email", choices=("none", "resend", "smtp"),
                   help="how mail can leave the server")
    p.add_argument("--paid-llm", action="store_true",
                   help="the model endpoint bills per call")
    p.add_argument("--public", action="store_true",
                   help="reachable from the internet")
    p.add_argument("--apply", action="store_true", help="write the result")
    p.add_argument("--force", action="store_true", help="with --apply, overwrite")
    p.set_defaults(fn=cmd_recommend)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
