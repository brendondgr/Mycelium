"""The cross-encoder rerank stage: device selection and reordering.

Like ``apps/scraper/tests/test_embedding_device.py``, these tests never import
fastembed or onnxruntime. ``cuda_available`` is the one seam that touches the
runtime and the fastembed constructor is injected through ``sys.modules``, so the
CUDA branches are exercised on a CPU-only box — which is what this host is, and
what CI is.

The reordering tests take a stub scorer, so they need no model, no GPU and no
database.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.content import reranking as rr


@dataclass
class FakeItem:
    """The three fields `Retrievable` requires; `_item_text` reads metadata."""

    id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None


def items(*specs: tuple[str, str]) -> list[FakeItem]:
    return [FakeItem(id=i, metadata={"title": t, "abstract": ""}) for i, t in specs]


class FakeCrossEncoder:
    """Records how fastembed was constructed and what batch size it was given."""

    instances: list[FakeCrossEncoder] = []
    fail_on_cuda = False

    def __init__(self, model_name, cuda=False, device_ids=None, **kwargs):
        if cuda and type(self).fail_on_cuda:
            raise RuntimeError("libcudart.so.12: cannot open shared object file")
        self.model_name = model_name
        self.cuda = cuda
        self.device_ids = device_ids
        self.batch_sizes: list[int] = []
        type(self).instances.append(self)

    def rerank(self, query, documents, batch_size=64, **kwargs):
        self.batch_sizes.append(batch_size)
        # Longer documents score higher: deterministic and easy to assert on.
        return [float(len(d)) for d in documents]


def _install_fake_fastembed():
    """Patch the fastembed cross-encoder module for the duration of a test."""
    root = types.ModuleType("fastembed")
    rerank_pkg = types.ModuleType("fastembed.rerank")
    cross = types.ModuleType("fastembed.rerank.cross_encoder")
    cross.TextCrossEncoder = FakeCrossEncoder
    rerank_pkg.cross_encoder = cross
    root.rerank = rerank_pkg
    return patch.dict(
        sys.modules,
        {
            "fastembed": root,
            "fastembed.rerank": rerank_pkg,
            "fastembed.rerank.cross_encoder": cross,
        },
    )


class ResolveDeviceTests(SimpleTestCase):
    def setUp(self):
        rr.reset_rerank_cache()
        FakeCrossEncoder.instances = []
        FakeCrossEncoder.fail_on_cuda = False

    @override_settings(RERANK_DEVICE="auto")
    def test_auto_uses_cuda_when_the_provider_is_available(self):
        with patch.object(rr, "cuda_available", return_value=True):
            self.assertEqual(rr.resolve_device(), (rr.CUDA, None))

    @override_settings(RERANK_DEVICE="auto")
    def test_auto_falls_back_to_cpu_without_a_provider(self):
        with patch.object(rr, "cuda_available", return_value=False):
            self.assertEqual(rr.resolve_device(), (rr.CPU, None))

    @override_settings(RERANK_DEVICE="cpu")
    def test_cpu_is_honored_even_on_a_cuda_host(self):
        with patch.object(rr, "cuda_available", return_value=True):
            self.assertEqual(rr.resolve_device(), (rr.CPU, None))

    @override_settings(RERANK_DEVICE="cuda")
    def test_explicit_cuda_degrades_to_cpu_when_unavailable(self):
        """A missing GPU runtime warns and degrades; it never crashes a run."""
        with patch.object(rr, "cuda_available", return_value=False):
            self.assertEqual(rr.resolve_device(), (rr.CPU, None))

    @override_settings(RERANK_DEVICE="auto", RERANK_DEVICE_ID="1")
    def test_device_id_selects_a_card(self):
        with patch.object(rr, "cuda_available", return_value=True):
            self.assertEqual(rr.resolve_device(), (rr.CUDA, 1))

    @override_settings(RERANK_DEVICE="nonsense")
    def test_unknown_device_falls_back_to_auto(self):
        with patch.object(rr, "cuda_available", return_value=True):
            self.assertEqual(rr.resolve_device(), (rr.CUDA, None))

    @override_settings(RERANK_DEVICE=None, EMBEDDING_DEVICE="cpu")
    def test_unset_rerank_device_inherits_the_embedding_device(self):
        """One host setting configures both models — see the module docstring."""
        with patch.object(rr, "cuda_available", return_value=True):
            self.assertEqual(rr.resolve_device(), (rr.CPU, None))

    @override_settings(
        RERANK_DEVICE=None, EMBEDDING_DEVICE="auto", EMBEDDING_DEVICE_ID="2"
    )
    def test_unset_device_id_inherits_the_embedding_card(self):
        with patch.object(rr, "cuda_available", return_value=True):
            self.assertEqual(rr.resolve_device(), (rr.CUDA, 2))

    def test_argument_overrides_the_setting(self):
        with (
            override_settings(RERANK_DEVICE="cuda"),
            patch.object(rr, "cuda_available", return_value=True),
        ):
            self.assertEqual(rr.resolve_device("cpu"), (rr.CPU, None))


class ScorerTests(SimpleTestCase):
    def setUp(self):
        rr.reset_rerank_cache()
        FakeCrossEncoder.instances = []
        FakeCrossEncoder.fail_on_cuda = False

    @override_settings(RERANK_DEVICE="cuda")
    def test_cuda_session_failure_degrades_to_cpu(self):
        """A driver mismatch must slow a run down, not take it out."""
        FakeCrossEncoder.fail_on_cuda = True
        with (
            _install_fake_fastembed(),
            patch.object(rr, "cuda_available", return_value=True),
        ):
            scorer = rr.get_scorer()
        self.assertIsNotNone(scorer)
        self.assertEqual(len(FakeCrossEncoder.instances), 1)
        self.assertFalse(FakeCrossEncoder.instances[0].cuda)

    @override_settings(RERANK_DEVICE="cuda", RERANK_DEVICE_ID="1")
    def test_cuda_session_is_built_on_the_requested_card(self):
        with (
            _install_fake_fastembed(),
            patch.object(rr, "cuda_available", return_value=True),
        ):
            rr.get_scorer()
        built = FakeCrossEncoder.instances[0]
        self.assertTrue(built.cuda)
        self.assertEqual(built.device_ids, [1])

    @override_settings(RERANK_DEVICE="cpu", RERANK_BATCH_SIZE_CPU=8)
    def test_batch_size_follows_the_device(self):
        with _install_fake_fastembed():
            scorer = rr.get_scorer()
            scorer("q", ["a", "bb"])
        self.assertEqual(FakeCrossEncoder.instances[0].batch_sizes, [8])

    @override_settings(RERANK_DEVICE="cpu")
    def test_the_session_is_cached_across_calls(self):
        with _install_fake_fastembed():
            rr.get_scorer()
            rr.get_scorer()
        self.assertEqual(len(FakeCrossEncoder.instances), 1)

    def test_a_missing_extra_disables_the_stage_rather_than_raising(self):
        with patch.object(rr, "_build_model", side_effect=ImportError):
            self.assertIsNone(rr.get_scorer())

    def test_an_unloadable_model_disables_the_stage_rather_than_raising(self):
        with patch.object(rr, "_build_model", side_effect=RuntimeError("boom")):
            self.assertIsNone(rr.get_scorer())


class EnabledForTests(SimpleTestCase):
    @override_settings(RERANK_ENABLED=False)
    def test_off_by_the_master_switch(self):
        self.assertFalse(rr.enabled_for("paper"))

    @override_settings(RERANK_ENABLED=True, RERANK_CONTENT_TYPES=("paper", "grant"))
    def test_on_for_listed_types(self):
        self.assertTrue(rr.enabled_for("paper"))
        self.assertTrue(rr.enabled_for("grant"))

    @override_settings(RERANK_ENABLED=True, RERANK_CONTENT_TYPES=("paper", "grant"))
    def test_off_for_unlisted_types(self):
        """Fellowships are absent by default — Q-031, see the module docstring."""
        self.assertFalse(rr.enabled_for("fellowship"))

    @override_settings(RERANK_ENABLED=True, RERANK_CONTENT_TYPES="paper, conference")
    def test_a_comma_string_is_accepted_from_the_environment(self):
        self.assertTrue(rr.enabled_for("conference"))
        self.assertFalse(rr.enabled_for("grant"))

    @override_settings(RERANK_ENABLED=True)
    def test_a_typeless_collection_never_reranks(self):
        """The eval harness scores a collection with no content type."""
        self.assertFalse(rr.enabled_for(None))


class RerankTests(SimpleTestCase):
    """Reordering only — a stub scorer, no model, no database."""

    def test_it_reorders_by_score_best_first(self):
        pool = items(("a", "x"), ("b", "xxx"), ("c", "xx"))
        order = rr.rerank("q", pool, score=lambda q, docs: [1.0, 3.0, 2.0])
        self.assertEqual(order, ["b", "c", "a"])

    def test_it_only_touches_the_head_and_never_promotes_the_tail(self):
        """A reranker that cannot see rank 3 must not be able to move it."""
        pool = items(("a", "x"), ("b", "x"), ("c", "x"), ("d", "x"))
        order = rr.rerank(
            "q", pool, score=lambda q, docs: [1.0, 9.0], depth=2
        )
        self.assertEqual(order, ["b", "a", "c", "d"])

    def test_ties_break_on_document_id_not_on_iteration_order(self):
        """EXP-2026-08-003 recorded a 'ranking' whose tie order was a hash."""
        pool = items(("z", "x"), ("a", "x"), ("m", "x"))
        order = rr.rerank("q", pool, score=lambda q, docs: [5.0, 5.0, 5.0])
        self.assertEqual(order, ["a", "m", "z"])

    def test_no_scorer_is_a_no_op(self):
        pool = items(("a", "x"), ("b", "y"))
        self.assertEqual(rr.rerank("q", pool, score=None), ["a", "b"])

    def test_an_empty_query_is_a_no_op(self):
        pool = items(("a", "x"), ("b", "y"))
        order = rr.rerank("   ", pool, score=lambda q, d: [9.0, 1.0])
        self.assertEqual(order, ["a", "b"])

    def test_an_empty_pool_returns_empty(self):
        self.assertEqual(rr.rerank("q", [], score=lambda q, d: []), [])

    def test_a_failing_scorer_keeps_the_fused_order(self):
        pool = items(("a", "x"), ("b", "y"))

        def boom(query, docs):
            raise RuntimeError("session died mid-batch")

        self.assertEqual(rr.rerank("q", pool, score=boom), ["a", "b"])

    def test_a_wrong_length_score_vector_keeps_the_fused_order(self):
        """Trusting a mismatched vector would silently mis-attribute scores."""
        pool = items(("a", "x"), ("b", "y"), ("c", "z"))
        order = rr.rerank("q", pool, score=lambda q, docs: [1.0, 2.0])
        self.assertEqual(order, ["a", "b", "c"])

    def test_it_scores_the_same_text_bm25_indexes(self):
        """One document, not two — the lexical channel and the reranker agree."""
        seen: dict[str, list[str]] = {}

        def capture(query, docs):
            seen["docs"] = list(docs)
            return [1.0] * len(docs)

        pool = [FakeItem(id="a", metadata={"title": "T", "abstract": "A"})]
        rr.rerank("q", pool, score=capture)
        self.assertEqual(seen["docs"], ["T A"])
