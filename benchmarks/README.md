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
python3 -m venv .venv-bench
.venv-bench/bin/pip install laya-mlx
.venv-bench/bin/python benchmarks/latency_bench.py --selftest
.venv-bench/bin/python benchmarks/latency_bench.py --batch-size 1  --repeats 50
.venv-bench/bin/python benchmarks/latency_bench.py --batch-size 16 --repeats 50
.venv-bench/bin/python benchmarks/latency_bench.py --batch-size 1 --full-context
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

| Config | Chip | P50 (ms) | P95 (ms) | q/s @ P50 | Published P50 (M3 Max) |
|---|---|---:|---:|---:|---:|
| 3 questions, short state, batch_size=1 | M1 Pro | 62.35 | 63.50 | 48.1 | 17.75 @ 1q |
| 3 questions, short state, batch_size=16 | M1 Pro | 50.19 | 50.94 | 59.8 | — |
| 3 questions, ~512-token state, b=1 | M1 Pro | 388.21 | 403.74 | 7.7 | 49.84 @ 1q |

**Findings (M1 Pro vs published M3 Max):**

- **Batching matters:** the ADIP workload sends 3 questions per call; batch_size=16
  collapses them into one forward pass and cuts P50 from 62.3 → 50.2 ms (−19%).
  Serving must load with `batch_size ≥ 3`.
- **Model footprint matches published:** peak process RSS 934.6 MiB vs the
  published 943.6 MiB peak MLX allocation. Load is ~0.5 s warm; the first load
  downloads the checkpoint (~163 s incl. download on this connection).
- **Short-context decisions are overhead-bound:** 3 rows at 93 padded tokens cost
  nearly the same per row as the published single-row latency once batched —
  fixed per-call work (prompt prep, tokenization, sync, formatting) dominates.
- **Full-context is compute/bandwidth-bound:** ~2.6× slower per row than the
  M3 Max figure (memory bandwidth 200 vs 400 GB/s class). Interactive requests
  must keep redacted states short; full-context work belongs in batch jobs.
- **Strict-mode probe budget shrinks on this hardware:** probes cost ~50 ms each
  (batched) here, not the ~18–50 ms the blueprint budgets for M3 Max-class —
  inline budgets should drop to 2–4 probes on M1 Pro-class nodes, or run async.
  Applies to every domain's policy probes — the engine, not the domain, sets
  this budget.
- **Determinism:** 100% identical answers JSON across repeated calls in all
  three configurations.

_(add rows from new runs as other hardware is measured; keep raw JSONs)_

## Gates (blueprint §9)

- decision-only P95 < 60 ms for a 3-question call
- 100% deterministic answers across repeated calls
