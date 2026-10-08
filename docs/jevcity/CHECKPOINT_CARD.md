# Checkpoint Card — `aac6fef/laya-typed-decisions-mlx`

Plan §Phase 6 ("Checkpoint card"). Reproducibility record for the pinned weights.

## Identity

| | |
|---|---|
| Hub repository | `aac6fef/laya-typed-decisions-mlx` |
| Snapshot revision (local cache) | `f9e501c2080cc57c13d6887820329758f5351125` |
| Upstream source (per `mlx_config.json`) | `convaiinnovations/laya-typed-decisions`, revision `f9ab0b228f0fc0f14d873dbc99038f135c2da1b2` |
| Format | `laya-mlx` format_version 1 |
| Weights file | `model.safetensors` — 842,609,225 bytes (~804 MiB), float16 |
| Dtype | float16 (`mlx_config.json` `dtype`, adapter `DTYPE = "float16"`) |
| Device | MPS (`normalize.DEVICE = "mps"`, Apple silicon only) |
| Encoder | `answerdotai/ModernBERT-large` (per `rl_agent_config.json`), max_len 1024 / head_max_len 256 |
| RL head | 2 layers, `act_costs.escalate = 0.5`, `cost_wrong_act = 3.0` |
| Calibration | temperature 1.0148–1.0575 (upstream, per-question-type table) |
| Fine-tune provenance | `fine_tuned_from_checkpoint: true`, 7313 updates, 1 epoch, 1.96 h, world_size 1 |

## Where it runs

- Cache path: `~/.cache/huggingface/hub` (HF standard layout, offline after first
  pull — demo needs no internet).
- CI: `.github/workflows/ci.yml` macos job restores cache keyed
  `hf-aac6fef-laya-mlx-${{ runner.os }}`; strict eval tier `pytest -m "model and not
  laya_live"`, live smoke tier `pytest -m laya_live`.
- Loaded lazily by `LayaAdapter` only in `LIVE` mode; `MOCK`/`CACHE` modes never
  touch the checkpoint (fallback ladder item 19).

## Reproducibility / determinism

- Adapter cache key: `state_hash + questions_hash + checkpoint + device + dtype`
  (plan §deterministic replay, signoff item 20).
- Eval repeats: determinism check passes (`evals/results/eval-jevcity-*.json`
  `"determinism": true`, repeats = 2, identical answers).
- Model versions recorded on every decision and audit entry: audit
  `model_versions.laya_checkpoint = aac6fef/laya-typed-decisions-mlx`,
  decision `laya.checkpoint` — enforced by `tests/jevcity/test_audit_phase4.py`.

## Provenance caveats (honest notes)

- Hub `License` metadata is not published for this repository — treat licensing as
  **unverified upstream**; this repo only pins and records the revision.
- `laya-serve` / HTTP sidecar claims (plan C1) are unverified; only the in-process
  laya-mlx load path is exercised (`tests/jevcity/test_laya_live.py`).
- Evaluated gate status: **C4 measured fail** (accuracy 0.5675, ECE 0.3528 vs
  0.70/0.15, n = 84) — see `LAYA_MODEL_CARD.md`; thresholds frozen.
