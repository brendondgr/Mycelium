"""Device selection for the local embedder (tools.retrieval.embedding).

These tests never import fastembed or onnxruntime: ``cuda_available`` is the one
seam that touches the runtime, and the fastembed constructor is injected via
``sys.modules``. So the suite exercises the CUDA branches on a CPU-only box.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from tools.retrieval import embedding as emb


class FakeTextEmbedding:
    """Records how fastembed was constructed and what batch size it was given."""

    instances: list[FakeTextEmbedding] = []
    fail_on_cuda = False

    def __init__(self, model_name, cuda=False, device_ids=None, **kwargs):
        if cuda and type(self).fail_on_cuda:
            raise RuntimeError("libcudart.so.12: cannot open shared object file")
        self.model_name = model_name
        self.cuda = cuda
        self.device_ids = device_ids
        self.batch_sizes: list[int] = []
        type(self).instances.append(self)

    def embed(self, texts, batch_size=256, **kwargs):
        self.batch_sizes.append(batch_size)
        return [[3.0, 4.0] for _ in texts]


def _install_fake_fastembed():
    """Patch ``sys.modules['fastembed']`` for the duration of a test."""
    module = types.ModuleType("fastembed")
    module.TextEmbedding = FakeTextEmbedding
    return patch.dict(sys.modules, {"fastembed": module})


class ResolveDeviceTests(SimpleTestCase):
    def setUp(self):
        emb.reset_embedding_cache()
        FakeTextEmbedding.instances = []
        FakeTextEmbedding.fail_on_cuda = False

    @override_settings(EMBEDDING_DEVICE="auto")
    def test_auto_uses_cuda_when_the_provider_is_available(self):
        with patch.object(emb, "cuda_available", return_value=True):
            self.assertEqual(emb.resolve_device(), (emb.CUDA, None))

    @override_settings(EMBEDDING_DEVICE="auto")
    def test_auto_falls_back_to_cpu_without_a_provider(self):
        with patch.object(emb, "cuda_available", return_value=False):
            self.assertEqual(emb.resolve_device(), (emb.CPU, None))

    @override_settings(EMBEDDING_DEVICE="cpu")
    def test_cpu_is_honored_even_on_a_cuda_host(self):
        with patch.object(emb, "cuda_available", return_value=True):
            self.assertEqual(emb.resolve_device(), (emb.CPU, None))

    @override_settings(EMBEDDING_DEVICE="cuda")
    def test_explicit_cuda_degrades_to_cpu_when_unavailable(self):
        """A missing GPU runtime must never crash a scan — it warns and degrades."""
        with patch.object(emb, "cuda_available", return_value=False):
            self.assertEqual(emb.resolve_device(), (emb.CPU, None))

    @override_settings(EMBEDDING_DEVICE="auto", EMBEDDING_DEVICE_ID="1")
    def test_device_id_selects_a_card(self):
        with patch.object(emb, "cuda_available", return_value=True):
            self.assertEqual(emb.resolve_device(), (emb.CUDA, 1))

    @override_settings(EMBEDDING_DEVICE="nonsense")
    def test_unknown_device_falls_back_to_auto(self):
        with patch.object(emb, "cuda_available", return_value=True):
            self.assertEqual(emb.resolve_device(), (emb.CUDA, None))

    def test_argument_overrides_the_setting(self):
        with (
            override_settings(EMBEDDING_DEVICE="cuda"),
            patch.object(emb, "cuda_available", return_value=True),
        ):
            self.assertEqual(emb.resolve_device("cpu"), (emb.CPU, None))


class EmbedderDeviceTests(SimpleTestCase):
    def setUp(self):
        emb.reset_embedding_cache()
        FakeTextEmbedding.instances = []
        FakeTextEmbedding.fail_on_cuda = False

    @override_settings(EMBEDDING_DEVICE="auto", EMBEDDING_BATCH_SIZE_GPU=512)
    def test_gpu_run_builds_a_cuda_session_with_the_gpu_batch_size(self):
        with (
            patch.object(emb, "cuda_available", return_value=True),
            _install_fake_fastembed(),
        ):
            vectors = emb.FastEmbedEmbedder()(["one", "two"])

        model = FakeTextEmbedding.instances[-1]
        self.assertTrue(model.cuda)
        self.assertEqual(model.batch_sizes, [512])
        # Vectors stay unit-normalized regardless of device (3,4) -> (0.6,0.8).
        self.assertAlmostEqual(vectors[0][0], 0.6, places=5)
        self.assertAlmostEqual(vectors[0][1], 0.8, places=5)

    @override_settings(EMBEDDING_DEVICE="cpu", EMBEDDING_BATCH_SIZE_CPU=32)
    def test_cpu_run_builds_a_cpu_session_with_the_cpu_batch_size(self):
        with (
            patch.object(emb, "cuda_available", return_value=True),
            _install_fake_fastembed(),
        ):
            emb.FastEmbedEmbedder()(["one"])

        model = FakeTextEmbedding.instances[-1]
        self.assertFalse(model.cuda)
        self.assertEqual(model.batch_sizes, [32])

    @override_settings(EMBEDDING_DEVICE="auto")
    def test_a_failed_cuda_session_falls_back_to_cpu(self):
        FakeTextEmbedding.fail_on_cuda = True
        with (
            patch.object(emb, "cuda_available", return_value=True),
            _install_fake_fastembed(),
        ):
            vectors = emb.FastEmbedEmbedder()(["one"])

        self.assertEqual(len(vectors), 1)
        self.assertFalse(FakeTextEmbedding.instances[-1].cuda)

    @override_settings(EMBEDDING_DEVICE="auto")
    def test_the_session_is_shared_across_embedder_instances(self):
        """The resolver builds an embedder per call; the GPU must load once."""
        with (
            patch.object(emb, "cuda_available", return_value=True),
            _install_fake_fastembed(),
        ):
            emb.FastEmbedEmbedder()(["one"])
            emb.FastEmbedEmbedder()(["two"])

        self.assertEqual(len(FakeTextEmbedding.instances), 1)

    @override_settings(EMBEDDING_DEVICE="auto")
    def test_reset_drops_the_cached_session(self):
        with (
            patch.object(emb, "cuda_available", return_value=True),
            _install_fake_fastembed(),
        ):
            emb.FastEmbedEmbedder()(["one"])
            emb.reset_embedding_cache()
            emb.FastEmbedEmbedder()(["two"])

        self.assertEqual(len(FakeTextEmbedding.instances), 2)

    def test_empty_batch_never_loads_the_model(self):
        with _install_fake_fastembed():
            self.assertEqual(emb.FastEmbedEmbedder()([]), [])
        self.assertEqual(FakeTextEmbedding.instances, [])


class DescribeDeviceTests(SimpleTestCase):
    def setUp(self):
        emb.reset_embedding_cache()

    @override_settings(EMBEDDING_DEVICE="auto")
    def test_describe_reports_the_resolved_device_without_loading(self):
        with patch.object(emb, "cuda_available", return_value=True):
            info = emb.describe_device()

        self.assertEqual(info["device"], emb.CUDA)
        self.assertEqual(info["requested"], "auto")
        self.assertEqual(info["batch_size"], emb.default_batch_size(emb.CUDA))
        self.assertEqual(info["session_providers"], [])
