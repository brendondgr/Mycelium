# Hardware

- Host: 20 CPU cores, 62 GB RAM, Quadro RTX 5000 (16 GB). BM25 and the arms
  are CPU-only; the GPU is used only if the optional fusion contrast encodes the
  pooled dense matrix.
- Corpus cache: `data/eval-cache/ir_datasets` (LongEval-Sci 2026 family),
  `data/eval-cache/embeddings` (only for the optional contrast).
- Model: TypeSafe `jev-1.13.0` over HTTPS; latency is network plus their
  inference. Concurrency 12 against a documented 1,200 requests/minute limit.
- Python 3.13, `eval/uv.lock`.
