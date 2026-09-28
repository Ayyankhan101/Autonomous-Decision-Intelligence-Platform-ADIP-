# ADIP Benchmarks

Local re-measurement of [laya-mlx](https://github.com/mizorewww/laya-mlx) latency
on the hardware ADIP actually targets, per blueprint §9 (Evaluation & Test
Strategy) and the Phase 0 week-3 deliverable.

**Scope:** measures the *engine*, not a domain — the timing numbers apply to
any question set (ticket triage, bug triage, PR routing, etc.; blueprint §5.1).
Only the question payload changes per domain; latency does not.

## Method (mirrors laya-mlx's checked-in BENCHMARKS.md)

- Fresh Python process per configuration (each batch size runs separately).
- 5 warmup iterations, excluded; 50 timed iterations, **every sample stored**.
- Timing boundary: end-to-end `agent.predict()` wall clock — prompt construction,
  tokenization, tensor construction, model execution, calibration, result
  formatting. Model loading / checkpoint download excluded.
- Determinism check: answers JSON from repeated identical calls hashed and
  compared; recorded per run.
- The published upstream numbers come from an M3 Max (40-core GPU, 128 GB).
  This machine is smaller — the point of this harness is measuring *our*
  hardware, not reproducing theirs.

## Run

```bash
uv sync --frozen                          # deps come from pyproject.toml / uv.lock
uv run python benchmarks/latency_bench.py --selftest
uv run python benchmarks/latency_bench.py --batch-size 1  --repeats 50
uv run python benchmarks/latency_bench.py --batch-size 16 --repeats 50
uv run python benchmarks/latency_bench.py --batch-size 24 --repeats 50   # +32, +48
uv run python benchmarks/latency_bench.py --batch-size 1 --full-context
```

Note: the ADIP triage workload sends 3 questions per call, so any
`batch_size >= 3` batches them into one forward pass — b5/b10 configs would
be redundant here. b1 vs b16 isolates the batching effect.

Results land in `benchmarks/results/latency-<chip>-<config>-<timestamp>.json`
with the full environment record and raw samples.

## Results

First measured run: **Apple M1 Pro (8-core CPU: 6P+2E, 14-core GPU, Metal 4), 16 GB unified memory, macOS 26.6.2, Python 3.13, MLX (laya-mlx), FP16** — 2026-09-23.
Raw timing samples: `benchmarks/results/latency-AppleM1Pro-*.json` (one JSON per config,
50 stored samples each, environment record + determinism check included).

| Config | Payload | P50 (ms) | P95 (ms) | q/s @ P50 | Published P50 (M3 Max) |
|---|---|---:|---:|---:|---:|
| 3 questions, short state, b=1 | v1 (3-option dept) | 62.35 | 63.50 | 48.1 | 17.75 @ 1q |
| 3 questions, short state, b=16 | v1 (3-option dept) | 50.19 | 50.94 | 59.8 | — |
| 3 questions, ~512-token state, b=1 | v1 (3-option dept) | 388.21 | 403.74 | 7.7 | 49.84 @ 1q |
| 3 questions, short state, b=1 | v2 (4-option dept) | 72.22 | 73.33 | 41.5 | 17.75 @ 1q |
| 3 questions, short state, b=16 | v2 | 61.57 | 62.10 | 48.7 | — |
| 3 questions, ~512-token state, b=1 | v2 | 374.15 | 375.39 | 8.0 | 49.84 @ 1q |
| short state, b=1 (repeat run, 09-25) | v2 | 71.67 | 72.30 | 41.9 | — |
| short state, b=16 (repeat run, 09-25) | v2 | 61.58 | 62.01 | 48.7 | — |
| short state, b=24 (09-26) | v2 | 61.53 | 62.44 | 48.8 | — |
| short state, b=32 (09-26) | v2 | 61.84 | 62.42 | 48.5 | — |
| short state, b=48 (09-26) | v2 | 61.39 | 62.05 | 48.9 | — |

**Findings (M1 Pro vs published M3 Max):**

- **Batching matters:** the ADIP workload sends 3 questions per call; batch_size=16
  collapses them into one forward pass: 72.2 → 61.6 ms P50 (−15%) on the v2
  payload (62.3 → 50.2 ms, −19%, on the historical v1 payload). Serving must
  load with `batch_size ≥ 3`.
- **Model footprint matches published:** peak process RSS 934.6 MiB vs the
  published 943.6 MiB peak MLX allocation. Load is ~0.5 s warm; the first load
  downloads the checkpoint (~163 s incl. download on this connection).
- **Short-context decisions are overhead-bound:** 3 rows at 93 padded tokens cost
  nearly the same per row as the published single-row latency once batched —
  fixed per-call work (prompt prep, tokenization, sync, formatting) dominates.
- **Full-context is compute/bandwidth-bound:** ~2.5× slower per row than the
  M3 Max figure on v2 (374.15 ms / 3 rows vs 49.84 ms @ 1q; memory bandwidth
  200 vs 400 GB/s class). Interactive requests must keep redacted states
  short; full-context work belongs in batch jobs.
- **Strict-mode probe budget shrinks on this hardware:** probes cost ~60 ms each
  (batched, v2) here, not the ~18–50 ms the blueprint budgets for M3 Max-class —
  inline budgets should drop to 2–4 probes on M1 Pro-class nodes, or run async.
  Applies to every domain's policy probes — the engine, not the domain, sets
  this budget.
- **Determinism:** 100% identical answers JSON across repeated calls in all
  eleven stored runs (payload v1/v2 artifacts, through 2026-09-26; the eval
  payload moved to v3 that day — these timing baselines predate it and should
  be re-run to restamp).
- **60 ms decision-only gate status — FAIL on this hardware, honestly:** the
  harness's 61.4–62.1 ms (b≥16) is a *repeated* short input that hits the
  runtime prefix cache. Distinct tickets — what serving actually sends — cost
  **79.5 ms P50 / 125.8 ms P95** (eval runner, 50 golden tickets × 2 passes,
  warmup excluded, payload v2) and **93.7 / 256.4 ms** end-to-end (200-call
  load test, payload v3, stamped — quiet machine; contended runs fail KPI).
  An ad-hoc token-scaling probe (20 iterations each) shows why: 135 tokens →
  48.5 ms, 483 → 132 ms, 810 → 204 ms — latency tracks input tokens, so
  `batch_size` past 16 changes nothing (61.39–61.84 ms across b16→b48). Honest
  options: M3 Max-class serving nodes, shorter states, fewer questions per
  call, or renegotiating the gate. Recorded, not massaged.

_(add rows from new runs as other hardware is measured; keep raw JSONs)_

> **Provenance note:** result JSONs generated before the 2026-09-23
> whole-system review carry no `payload_version` field and used the 3-option
> department payload (the old b1 file also carries the pre-fix
> `peak_process_rss_mb` key name). All post-fix runs stamp `payload_version`
> and `question_set_sha256`; only those are baseline-eligible. Current serving
> payload is **v3** (`golden-v2.0.json`, sales criteria enriched) — every
> stored run here carries v1/v2 stamps, so cross-version latency comparisons
> need a fresh run, not a re-quote.

## Result file status

| Class | Files | Rule |
|---|---|---|
| **CURRENT** | `latency-AppleM1Pro-b1-20260925T171408.json`, `b16-20260925T171411.json`, `fullctx-20260923T174239.json`, `b24/b32/b48-20260926T*.json` | use for performance claims/reports |
| **ARCHIVED** | `archive/` (b1/b16 2026-09-23 runs, `fullctx-20260923T141617`) | superseded — **do not use** (see `archive/README.md`) |

## Gates (blueprint §9)

- decision P50 ≤ 100 ms for a 3-question call (D6; the original
  decision-only P95 < 60 ms was retired — unreachable over distinct inputs,
  evidence in README "Eval gates")
- 100% deterministic answers across repeated calls
