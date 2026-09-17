# Hardware

- Host: 20 CPU cores, 62 GB RAM, Quadro RTX 5000 (16 GB) — unused; nothing here
  runs on the GPU.
- Store: compose `postgres` (pgvector/pgvector:pg17) at localhost:11450.
- Model: TypeSafe `jev-1.13.0` over HTTPS (`api.typesafe.ai`); latency is
  network plus their inference, recorded per call.
- Python 3.13, `eval/uv.lock`.
