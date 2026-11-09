"""Check the decision backend, and measure its throughput.

    uv run --project web/backend python web/backend/manage.py decision_check
    … decision_check --url http://127.0.0.1:8080 --calls 64 --concurrency 8

Prints which backend the ``[decision]`` switch resolves to and why, the port's
protocol and model, then asks a fixed hand-written question (a yes/no and a
four-level score, the shapes the slate rerank asks) ``--calls`` times with
``--concurrency`` in flight, and reports the answers, latency percentiles and
calls per second. Nothing from the database is ever sent. ``--strict`` exits
non-zero when the backend is off or any call fails.

Throughput numbers this prints are measurements: record them in an experiment
folder before quoting them (``docs/research/AGENT_INSTRUCTIONS.md``).
"""

from __future__ import annotations

import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

SAMPLE_STATE = {
    "researcher": "A computational neuroscientist who models neural population "
    "dynamics from two-photon calcium imaging.",
    "strand": {
        "label": "Neural population dynamics",
        "interests": ["calcium imaging", "latent dynamical systems"],
    },
    "opportunity": {
        "title": "Inferring latent dynamics from calcium imaging with switching "
        "linear dynamical systems",
        "abstract": "We fit recurrent switching linear dynamical systems to "
        "population calcium recordings from mouse visual cortex.",
    },
}


def _questions():
    from apps.core.decisions import score, yesno

    return {
        "worth": yesno(
            "Is this item worth this researcher's attention today, for this strand?",
            true="It matches the strand's interests specifically.",
            false="It is generic or about a different field.",
        ),
        "fit": score(
            "Where does this item sit for this strand?",
            ["Skip: off-topic", "File: later", "Skim: relevant", "Read: strong match"],
        ),
    }


class Command(BaseCommand):
    help = "Check the [decision] backend and measure its latency and throughput."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--backend",
            choices=("jev", "port"),
            default=None,
            help="Override the configured backend for this check.",
        )
        parser.add_argument(
            "--url", default=None, help="Override [decision] port_url for this check."
        )
        parser.add_argument(
            "--protocol",
            choices=("auto", "decide", "openai"),
            default=None,
            help="Override [decision] port_protocol.",
        )
        parser.add_argument(
            "--model", default=None, help="Override [decision] port_model."
        )
        parser.add_argument("--calls", type=int, default=1)
        parser.add_argument("--concurrency", type=int, default=1)
        parser.add_argument(
            "--json",
            dest="json_out",
            default=None,
            help="Also write a JSON summary of the run to this path.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit non-zero when off or any call fails.",
        )

    def handle(self, *args: object, **options) -> None:
        from apps.core import decisions

        cfg = self._effective(options)
        backend, reason = decisions.resolve(cfg)
        self.stdout.write(self.style.MIGRATE_HEADING("Decision backend"))
        self.stdout.write(f"  configured = {decisions.configured(cfg)!r}")
        self.stdout.write(f"  resolved   = {backend!r} ({reason})")
        self.stdout.write(f"  TYPESAFE_API_KEY set = {bool(cfg.TYPESAFE_API_KEY)}")
        self.stdout.write(f"  port_url   = {cfg.DECISION_PORT_URL!r}")
        if backend == decisions.OFF:
            self.stdout.write("  No decision model: slates keep their fused order.")
            if options["strict"]:
                raise CommandError(f"decision backend is off: {reason}")
            return

        client = decisions.build_decision_client(cfg, component="decision_check")
        try:
            if backend == decisions.PORT:
                self.stdout.write(f"  protocol   = {client.inner.protocol!r}")
            self.stdout.write(f"  model      = {client.model!r}")
        except Exception as exc:  # noqa: BLE001 — surface the real reason
            self.stderr.write(
                self.style.ERROR(f"  Unreachable: {type(exc).__name__}: {exc}")
            )
            if options["strict"]:
                raise CommandError("decision backend unreachable") from exc
            return

        calls = max(1, int(options["calls"]))
        workers = max(1, min(int(options["concurrency"]), calls))
        questions = _questions()

        def one(_i):
            started = time.perf_counter()
            try:
                result = client.ask(SAMPLE_STATE, questions)
            except Exception as exc:  # noqa: BLE001 — counted, not raised
                return None, (time.perf_counter() - started) * 1000, exc
            return result, (time.perf_counter() - started) * 1000, None

        self.stdout.write(
            self.style.MIGRATE_HEADING(f"\nAsking {calls} time(s), {workers} in flight")
        )
        wall_started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(one, range(calls)))
        wall = time.perf_counter() - wall_started

        ok = [(r, ms) for r, ms, err in results if err is None]
        errors = [err for _r, _ms, err in results if err is not None]
        if ok:
            first = ok[0][0].answers_as_dicts()
            self.stdout.write(f"  p(worth)   = {first['worth'].get('noul')!r}")
            self.stdout.write(
                f"  fit        = {first['fit'].get('score')!r} "
                f"{first['fit'].get('probabilities')!r}"
            )
            latencies = sorted(ms for _r, ms in ok)
            p50 = statistics.median(latencies)
            p95 = latencies[min(len(latencies) - 1, round(0.95 * (len(latencies) - 1)))]
            self.stdout.write(f"  latency    = p50 {p50:.0f} ms, p95 {p95:.0f} ms")
            self.stdout.write(
                f"  throughput = {len(ok) / wall:.2f} calls/s "
                f"({len(ok)} ok in {wall:.1f} s)"
            )
        for err in errors[:3]:
            self.stderr.write(
                self.style.ERROR(f"  failed: {type(err).__name__}: {err}")
            )
        self.stdout.write(f"  failures   = {len(errors)}/{calls}")
        if errors and options["strict"]:
            raise CommandError(f"{len(errors)} of {calls} calls failed")
        if not errors:
            self.stdout.write(self.style.SUCCESS("  Decision backend answers."))
        if options.get("json_out"):
            self._write_json(
                options["json_out"], client, backend, calls, workers, wall, ok, errors
            )

    @staticmethod
    def _write_json(path, client, backend, calls, workers, wall, ok, errors) -> None:
        import json
        from pathlib import Path

        latencies = sorted(ms for _r, ms in ok)

        def pct(q):
            if not latencies:
                return None
            return round(
                latencies[min(len(latencies) - 1, round(q * (len(latencies) - 1)))], 1
            )

        server_ms = sorted(r.latency_ms for r, _ms in ok)
        summary = {
            "backend": backend,
            "model": client.model,
            "protocol": getattr(getattr(client, "inner", None), "protocol", None)
            if backend == "port"
            else None,
            "calls": calls,
            "concurrency": workers,
            "ok": len(ok),
            "failures": len(errors),
            "wall_seconds": round(wall, 3),
            "throughput_calls_per_s": round(len(ok) / wall, 3) if wall else None,
            "latency_ms_p50": pct(0.5),
            "latency_ms_p95": pct(0.95),
            "latency_ms_max": round(latencies[-1], 1) if latencies else None,
            "client_latency_ms_mean": round(sum(server_ms) / len(server_ms), 1)
            if server_ms
            else None,
            "errors": [f"{type(e).__name__}: {e}"[:200] for e in errors[:5]],
        }
        Path(path).write_text(json.dumps(summary, indent=1))

    @staticmethod
    def _effective(options) -> SimpleNamespace:
        """Django settings with this run's overrides on top (never written back)."""
        names = (
            "DECISION_BACKEND",
            "TYPESAFE_API_KEY",
            "TYPESAFE_MODEL",
            "TYPESAFE_BASE_URL",
            "TYPESAFE_TIMEOUT",
            "TYPESAFE_MAX_RETRIES",
            "DECISION_PORT_URL",
            "DECISION_PORT_PROTOCOL",
            "DECISION_PORT_MODEL",
            "DECISION_PORT_API_KEY",
            "DECISION_PORT_TIMEOUT",
        )
        cfg = SimpleNamespace(**{n: getattr(settings, n, "") for n in names})
        if options.get("backend"):
            cfg.DECISION_BACKEND = options["backend"]
        if options.get("url") is not None:
            cfg.DECISION_PORT_URL = options["url"]
            if not options.get("backend"):
                cfg.DECISION_BACKEND = "port"
        if options.get("protocol"):
            cfg.DECISION_PORT_PROTOCOL = options["protocol"]
        if options.get("model") is not None:
            cfg.DECISION_PORT_MODEL = options["model"]
        return cfg
