# EXP-2026-11-009 — Issues

1. **Dirty tree.** Only this folder was new at run time; another session's
   uncommitted `docs/changelog.md` line and related-work notes were present and
   are not read here.
2. **Analysis bug, fixed before any number was recorded.** The first
   `analyse.py` keyed controls by (content, theme, control), and an item in two
   themes' top 3 can draw the same control theme twice, so two controls
   collapsed and the d3 alignment raised a `KeyError`. Controls are now keyed
   with their home theme too, and the script asserts no keys collide.
3. **First server start without `--alias`** reported the model by file path;
   restarted with `--alias qwen3-4b-q4_k_m` before the recorded run (only a
   2-call smoke check used the first start).
4. **Binaries and model live outside the repository** under
   `~/.local/share/mycelium-decision/` (llama.cpp `b11912` and the GGUF, both
   verified against their published SHA-256).
