#!/bin/sh
# EXP-2026-11-016: every counted configuration, one process at a time.
cd "$(dirname "$0")/../../../../.." || exit 1
E=docs/research/experiments/EXP-2026-11-016-agent-gate-replication
for seed in 101 202 303; do
  for arm in gate prompt_only; do
    for model in instance second; do
      echo "== $(date -u +%H:%M:%S) seed=$seed arm=$arm model=$model"
      docker compose run --rm --no-deps -T --user "$(id -u):$(id -g)" -e HOME=/tmp \
        -v "$PWD/docs/research:/app/docs/research" -e EVAL2_LLM_MODEL=default-model-2 \
        backend uv run --no-sync --project web/backend python \
        $E/code/run_gate.py --seed $seed --arm $arm --model $model --reps 3 --conc 3 --tag main \
        2>&1 | grep -v -e onnxruntime -e '^Traceback' -e '^  ' | grep -E '^[a-z-]+ [0-9] (True|False)|Error|error' | tail -60
    done
  done
done
echo "== done $(date -u +%H:%M:%S)"
