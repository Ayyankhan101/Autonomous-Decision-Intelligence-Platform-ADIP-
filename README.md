# Autonomous Decision Intelligence Platform (ADIP)

**A decision intelligence platform blueprint built on [Laya](https://huggingface.co/convaiinnovations/laya) typed decision models, served locally via the [laya-mlx](https://github.com/mizorewww/laya-mlx) runtime — free, Apache-2.0, and private by architecture.**

> Status: **planning / blueprint phase**. The full technical blueprint lives in [`explaination-of-the-project.md`](explaination-of-the-project.md) (mirrored in [`professtional-writing-end-sem-project.md`](professtional-writing-end-sem-project.md)). Implementation starts with the Phase 0 MVP (below).

---

## What ADIP does

Turn a **text state** into typed, calibrated, auditable decisions:

```text
choice → probabilities over named options        (route this ticket: billing | technical | sales)
score  → expected rubric level over ordered tiers (urgency: 0–2)
noul   → P(true) for a proposition               (does the customer want money back?)
```

Wrapped in a six-stage pipeline:

```text
                       request (text state)
                              │
                              ▼
                ┌──────────────────────────────┐
                │  1 · PRIVACY SCAN            │ Presidio PII redaction
                │     30–50 ms                 │ [PERSON] / [EMAIL] placeholders
                └──────────────┬───────────────┘
                               ▼
                ┌──────────────────────────────┐
                │  2 · FAIRNESS SCREEN         │ rules + parity checks
                │     10–20 ms                 │ flag → never auto-decide
                └──────────────┬───────────────┘
                               ▼
                ┌──────────────────────────────┐
                │  3 · TYPED DECISION          │ ONE batched laya.predict call
                │     18–45 ms                 │ choice + score + noul together
                └──────────────┬───────────────┘
                               ▼
                ┌──────────────────────────────┐
                │  4 · POLICY ROUTER  <1 ms    │ versioned thresholds
                └──────────────┬───────────────┘
                     p ≥ 0.90  │  mid-band        high entropy /
                  ┌────────────┼─────────┐  fairness flag
                  ▼            ▼         ▼
               AUTO_DECIDE   REVIEW   ESCALATE
                  └────────────┼─────────┘
                               ▼
                ┌──────────────────────────────┐
                │  5 · EXPLANATION             │ templates + probability
                │     5–10 ms                  │ distributions (no LLM prose)
                └──────────────┬───────────────┘
                               ▼
                ┌──────────────────────────────┐
                │  6 · AUDIT LOG               │ async · immutable · replayable
                └──────────────────────────────┘

            every stage's latency budget: blueprint §3 / §10
```

End-to-end target: **≤ 150 ms P50** (standard mode), **≤ 400 ms P95**; strict mode adds bounded counterfactual probes (blueprint §10).

## Architecture at a glance

```text
┌────────────────────────────────────────────────────────────────┐
│  PRESENTATION    FastAPI REST API · dashboard · reports        │
├────────────────────────────────────────────────────────────────┤
│  PIPELINE        privacy → fairness → laya → policy →          │
│                  explanation → audit      (the 6 stages above) │
├────────────────────────────────────────────────────────────────┤
│  INTELLIGENCE    laya-mlx Agent · MLX FP16 · ~0.9 GiB          │
│                  bidirectional encoder → decision heads →      │
│                  probabilities   (choice · score · noul)       │
├────────────────────────────────────────────────────────────────┤
│  DATA            SQLite→Postgres audit log · Prometheus metrics│
└────────────────────────────────────────────────────────────────┘
     all of it on one Apple Silicon Mac — nothing leaves the box
```

## Why laya-mlx (and not a cloud LLM API)

| | Cloud LLM API (v1 idea) | laya-mlx (v2) |
|---|---|---|
| Cost per decision | API tokens | **$0** marginal, ~$0.000002 hardware amortization |
| Data egress | state leaves the premises | **zero** — all inference is local |
| Output surface | free-text JSON to validate | constrained typed answers — nothing generated to go off-script |
| License / stack | proprietary | Apache-2.0, MLX, no PyTorch runtime, no cloud API |

## Performance (verified against the repo's checked-in `BENCHMARKS.md`)

M3 Max, 40-core GPU, 128 GiB, MLX 0.32.2, FP16, end-to-end (prompt → tokenization → inference → calibration → formatting; load excluded). One machine, one run per configuration.

| Metric | Laya 421M (English) | Multilingual 322M | Typed-decisions 421M |
|---|---|---|---|
| P50 / P95, 1 short question | **17.75 / 21.45 ms** | 10.91 / 19.48 ms | 16.17 / 17.74 ms |
| P50, 1 full-context question | 49.84 ms @ 512 tok | 43.50 ms @ 1,024 tok | 99.95 ms @ 1,024 tok |
| Throughput, 50-question batch-64 | 143.3 q/s | 402.2 q/s | 153.2 q/s |
| Peak MLX allocation, 1 short question | 943.6 MiB | 687.6 MiB | 943.6 MiB |
| Context limit | 512 tokens | 1,024 tokens | 1,024 tokens |

> ⚠️ **Discrepancy note:** the laya-mlx README headline (13.42 / 7.39 ms) does **not** match the repo's own `BENCHMARKS.md` run (17.75 / 10.91 ms). This project quotes `BENCHMARKS.md` and re-measures on its own hardware before citing anything externally. The batch throughput fixture cycles repeated question templates — it is not per-request serving latency.

## Honest limitations (full list: blueprint §8)

1. **Apple Silicon only** — MLX needs Metal; no Linux/Windows/cloud nodes, no Docker GPU passthrough on macOS. Inference runs bare-metal on macOS under `launchd`.
2. **Triage-style pretrained checkpoints** — not trained on credit/clinical outcomes; other domains need upstream RLCD fine-tuning, gated on eval.
3. **Confidence ≠ accuracy** — calibrated probability is a distribution property, not a promise; the policy router (AUTO / REVIEW / ESCALATE) exists for exactly this.
4. **Temperature clamping** — the runtime clamps calibration temperatures to [0.5, 5.0] and warns; ADIP logs every clamped bucket.
5. **No free-text output** — explanations are assembled from distributions + perturbation attribution, not generated prose.

## Platform (planned)

```text
                 ┌────────────────┐
   clients ────▶ │     nginx      │  TLS · load balancing
                 └───────┬────────┘
           ┌─────────────┼─────────────┐
           ▼             ▼             ▼
     ┌───────────┐ ┌───────────┐ ┌───────────┐
     │ Mac node 1│ │ Mac node 2│ │ Mac node N│  bare-metal macOS
     │ FastAPI   │ │ FastAPI   │ │ FastAPI   │  launchd keepalive
     │ laya FP16 │ │ laya FP16 │ │ laya FP16 │  ~56 decisions/s each
     └─────┬─────┘ └─────┬─────┘ └─────┬─────┘  (17.75 ms/call)
           └─────────────┼─────────────┘
                         ▼
          ┌──────────────────────────────┐
          │  Postgres audit log          │  immutable · replayable
          │  Prometheus / Grafana        │  ECE + drift monitors
          └──────────────────────────────┘
```

- **Runtime:** Python 3.11+, `uv`, `laya-mlx` with pinned checkpoint revisions + weight checksums
- **Serving:** FastAPI; one uvicorn worker per agent; nginx across Mac nodes for scale-out
- **Privacy:** Microsoft Presidio redaction before the encoder; k-anonymity on exports
- **Storage:** SQLite (WAL) → PostgreSQL; Prometheus `/metrics` + Grafana
- **CI:** GitHub Actions `macos-14` arm64 (unit tier); nightly fidelity/calibration/latency benchmarks on real hardware

## Roadmap

| Phase | Weeks | Deliverable |
|---|---|---|
| **0 — MVP** | 1–4 | Ticket-triage demo: privacy → laya → policy → explanation → audit, P50 ≤ 150 ms, replayable audit log, honest eval report |
| **1 — Hardening** | 5–10 | Counterfactual engine, fairness CI gates, Postgres, multilingual Router with logged routing evidence |
| **2 — Extension** | 11–16 | Second use case, RLCD fine-tuning exploration (eval-gated), packaging, load tests |
| **3 — Stretch** | post-sem | Multi-node fleet. Explicitly not promised: SOC 2, FedRAMP, marketplace, 10k req/s clusters |

## Docs

- [`explaination-of-the-project.md`](explaination-of-the-project.md) — full technical blueprint (architecture, schemas, eval strategy, cost model)
- [`professtional-writing-end-sem-project.md`](professtional-writing-end-sem-project.md) — mirror of the blueprint for the end-sem deliverable

## Attribution & licensing

- **Laya** model + pretrained weights: [Convai Innovations](https://huggingface.co/convaiinnovations) (upstream: `NandhaKishorM/laya`)
- **laya-mlx**: independent Apache-2.0 MLX port by [mizorewww](https://github.com/mizorewww/laya-mlx) — not an official Convai release
- MLX: Apple's open-source array framework; ModernBERT / mmBERT encoders under their respective licenses

*Fast, local, constrained — and honest about what it does not know.*
