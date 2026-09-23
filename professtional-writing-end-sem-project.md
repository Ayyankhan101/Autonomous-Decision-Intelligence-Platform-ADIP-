# Autonomous Decision Intelligence Platform (ADIP)
## Technical Blueprint v2 — Laya-MLX Edition

> **Revision note (v2):** This blueprint replaces the proprietary "Jev / System One" cloud API with **Laya**, an open-weight typed decision model, running locally via the **laya-mlx** MLX runtime (https://github.com/mizorewww/laya-mlx). Every runtime claim in this document was verified against the laya-mlx repository (September 2026). What changed:
> - Inference: cloud API ($42/B tokens) → free, local, Apache-2.0, Apple Silicon MLX
> - Latency: 70–500 ms claimed → 10.9–17.8 ms measured (P50, end-to-end, 0 output tokens — per the repo's checked-in BENCHMARKS.md, not the README headline)
> - Deployment: Kubernetes/Istio/multi-region cloud → Apple Silicon-first, bare-metal macOS
> - "Zero hallucinations" overclaim → honest "constrained typed outputs" mechanism
> - Flagship use case: loan approval (out of distribution) → support-ticket triage (in distribution), loan approval demoted to fine-tuning stretch goal
> - Added: Constraints & Honest Limitations, Evaluation & Test Strategy, MVP tier, recomputed cost model
> - Removed: Kafka, Istio, Pinecone/Weaviate, 52-week/20-engineer roadmap, token-based pricing tiers

---

## 1. Vision & Overview

**Combine multiple areas:** Bias & Fairness + Data Privacy + XAI + MLOps + Business Analytics

**Vision:** Build a decision intelligence platform that uses **Laya** (a typed decision model, served locally through the **laya-mlx** runtime — upstream literally aliases `predict` as `system_one`) as the "brain" for automated decision-making across an organization.

**Unique value proposition (honest version):**

- **Blazing fast:** 17.75 ms P50 / 21.45 ms P95 for a short typed decision (Laya 421M, MLX FP16, 1 question, M3 Max — BENCHMARKS.md); 10.91 ms P50 with the multilingual checkpoint. Zero output tokens — decisions are not generated, they are scored.
- **Calibrated & auditable:** every answer ships as a probability distribution over named options, ordered rubric levels, or P(true). The runtime clamps pathological calibration temperatures to [0.5, 5.0] and warns on every clamped bucket.
- **No generated JSON, no hallucinated answers:** outputs are constrained to the declared option set. There is no free-text decoding step to go off the rails.
- **Private by architecture:** all inference is local (MLX, no cloud API, no PyTorch runtime). Sensitive state never leaves the machine.
- **Free:** Apache-2.0 runtime and weights. Marginal cost per decision is $0; only hardware amortization remains.

**Target users:** teams that need a fast, auditable **choice / score / probability** out of a text state — support triage, ticket routing, content moderation rubrics, lead scoring, document screening — especially where data cannot leave the premises.

**Explicitly not the target:** free-form text generation. Laya does not write prose. If you need generated rationales, add a separate LLM stage; ADIP's explanations are assembled deterministically instead (Section 4.4).

---

## 2. Runtime Facts: What laya-mlx Actually Provides

Verified from the laya-mlx repository. These numbers anchor every budget in this document.

| Property | Laya 421M (English) | Multilingual 322M | Typed-decisions 421M |
|---|---|---|---|
| Encoder | ModernBERT-large | mmBERT-base | ModernBERT-large |
| Context limit (state + questions) | 512 tokens | 1,024 tokens | 1,024 tokens |
| P50 / P95, one short question (MLX FP16) | 17.75 / 21.45 ms | 10.91 / 19.48 ms | 16.17 / 17.74 ms |
| P50, one FULL-context question (MLX FP16) | 49.84 ms @ 512 tok | 43.50 ms @ 1,024 tok | 99.95 ms @ 1,024 tok |
| Throughput, 50-question batch (batch_size=64) | 143.3 q/s | 402.2 q/s | 153.2 q/s |
| Peak MLX allocation, one short question | 943.6 MiB | 687.6 MiB | 943.6 MiB |
| Pre-converted checkpoint | `aac6fef/laya-mlx` | `aac6fef/laya-multilingual-mlx` | `aac6fef/laya-typed-decisions-mlx` |

**Benchmark provenance (important):** the laya-mlx README headline (13.42 / 7.39 ms) does **not** match the repo's own checked-in `BENCHMARKS.md` run (17.75 / 10.91 ms, laya / multilingual, MLX FP16, 1 short question). This document quotes **BENCHMARKS.md** and flags the discrepancy. BENCHMARKS.md also states these are one development machine, one run per configuration — all figures must be re-measured on ADIP's own hardware before being cited externally. The 50-question throughput fixture cycles three question templates (batch throughput, not per-request serving latency).

**Question types (the entire output surface):**

```text
choice → probabilities over named options        {label, probability, distribution}
score  → probabilities over ordered rubric levels and their expected score
noul   → P(true) for a proposition
```

**Mechanism:** `state + typed questions → bidirectional encoder → decision heads → probabilities`. No token-by-token decoding. Question rows are batched independently; each question gets its own encoder computation (no cross-question hidden-state reuse is claimed).

**Non-negotiable platform constraint:** Apple Silicon (MLX, Metal), macOS 14+, Python 3.11+. Measured environment: macOS, Python 3.12, MLX 0.32.2. This runtime does not run on Linux/Windows cloud nodes. The whole architecture in this document is built around that fact.

**Provenance:** Laya model and pretrained weights are by Convai Innovations (upstream: `NandhaKishorM/laya`); laya-mlx is an independent Apache-2.0 MLX port (mizorewww), not an official Convai release. Fine-tuning (RLCD) lives upstream; the port ships inference and conversion only.

**Quick reference (from the repo):**

```python
import laya_mlx as laya

agent = laya.load("aac6fef/laya-mlx")          # FP16 default; ~0.9 GiB resident
result = agent.predict(
    "I was billed twice. Please refund the duplicate.",
    {
        "department": {
            "type": "choice",
            "instructions": "Who should handle this?",
            "criteria": ["billing", "technical", "sales"],
        },
        "urgency": {
            "type": "score",
            "instructions": "How urgent is this request?",
            "criteria": ["not urgent", "soon", "critical"],
        },
        "refund": {"type": "noul", "instructions": "Does the customer ask for money back?"},
    },
)
print(result["answers"])
```

Useful runtime features ADIP uses: `Router` (language routing across the three checkpoints, re-entrant-lock model lifecycle), `predict_shortlist` (cosine shortlisting for large option sets), `embed_fn_from_agent` (mean-pooled encoder embeddings, no extra weights), opt-in `compile=True` / `pad_to_multiple=16` / `cache_prompts=True` (bounded prefix cache of 128 questions, ~6.5% measured gain on the Snake workload), `device="gpu"|"cpu"`, pinned Hub revisions for reproducibility.

---

## 3. System Architecture Overview

```text
┌──────────────────────────────────────────────────────────────────┐
│                        PRESENTATION LAYER                        │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐  │
│  │ Dashboard  │  │ REST API   │  │ Alerts     │  │ Reports    │  │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘  │
└──────────────────────────────┬───────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────┐
│                       ORCHESTRATION LAYER                        │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                  DECISION WORKFLOW ENGINE                  │  │
│  │  • Routes requests through the 6-stage pipeline            │  │
│  │  • One batched laya.predict call per decision              │  │
│  │  • Applies policy router (auto / review / escalate)        │  │
│  │  • Aggregates results with confidence weighting            │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬───────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────┐
│                 INTELLIGENCE LAYER (LAYA CORE)                   │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐  │
│  │  Decision  │  │  Fairness  │  │  Privacy   │  │ Explain-   │  │
│  │  Engine    │  │  Detector  │  │  Scanner   │  │ ability    │  │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘  │
│                  ┌────────────┐  ┌────────────┐                  │
│                  │ Monitoring │  │   Audit    │                  │
│                  │  & Drift   │  │  Reporter  │                  │
│                  └────────────┘  └────────────┘                  │
└──────────────────────────────┬───────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────┐
│                           DATA LAYER                             │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐  │
│  │Decision Log│  │Time-Series │  │ Audit DB   │  │ Eval Data  │  │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

**The core decision flow (one decision = one laya call):**

```text
request (text state)
   │
   ▼
[Privacy scan]  Presidio PII detect + redact          ── 30–50 ms
   │
   ▼
[Fairness screen] rule/parity screen on live traffic  ── 10–20 ms
   │
   ▼
[laya predict]  all typed questions in ONE batched    ── 18–45 ms
   │            call (choice + score + noul)
   ▼
[Policy router] thresholds → AUTO / REVIEW / ESCALATE ── <1 ms
   │
   ▼
[Explanation]  template assembly from probabilities   ── 5–10 ms
   │
   ▼
response                      [Audit + metrics: async, off critical path]
```

Note what is gone from v1: there is no "parallel Jev queries" stage. One `predict` call answers every typed question for a decision in a single batched forward pass.

---

## 4. Component Deep Dive

### 4.1 Decision Engine (typed decision core)

**Purpose:** turn a text state into typed, calibrated answers plus a policy decision.

**How laya is used:**
- One `agent.predict(state, questions)` call per decision. All questions (choice + score + noul) are batched inside that call; `batch_size=16` default, raise it when memory allows.
- The decision is derived from the typed answers by an explicit, versioned policy — never by generated text. Example triage policy: `department` (choice) routes the ticket; `urgency` (score, 0–2) sets SLA; `refund` (noul) gates the refund workflow.
- Hot paths can opt into `compile=True, cache_prompts=True, pad_to_multiple=16` at load time. First call pays a compilation cost; measure before enabling per workload.

**Output schema:**

```typescript
interface TypedAnswer {
  question: string;
  kind: "choice" | "score" | "noul";
  selected?: string;                        // choice: selected option label
  probability?: number;                     // choice: P(selected); noul: P(true)
  distribution?: Record<string, number>;    // choice: full option distribution
  expected_score?: number;                  // score: expected zero-based rubric level
}

interface DecisionOutput {
  decision_id: string;                      // uuid v7 (time-ordered, index-friendly)
  timestamp: string;                        // ISO 8601
  decision_type: "AUTO_DECIDE" | "REVIEW" | "ESCALATE";
  answers: TypedAnswer[];
  policy: {
    policy_version: string;                 // thresholds are versioned, never magic
    thresholds: { auto: number; review: number; escalate: number };
  };
  confidence: {
    top_probability: number;                // calibrated — NOT a guarantee of accuracy
    margin: number;                         // top-1 minus top-2 option probability
    entropy: number;                        // normalized entropy of the distribution
  };
  attribution?: Array<{                     // strict mode only (Section 4.4)
    field: string;
    delta_probability: number;              // change in chosen option's probability
  }>;
  metadata: {
    runtime: "laya-mlx";
    checkpoint: string;                     // e.g. "aac6fef/laya-mlx" + pinned revision
    dtype: "float16" | "float32";
    processing_time_ms: number;
    state_token_estimate: number;           // guard against the 512/1024 context limit
    input_hash: string;                     // sha256 of redacted state, for audit join
  };
}
```

**Default routing thresholds (placeholders — calibrate on the golden set, Section 9):** `AUTO_DECIDE` when `top_probability ≥ 0.90` and `margin ≥ 0.20`; `REVIEW` when in the band; `ESCALATE` when entropy is high or a fairness flag fired.

### 4.2 Fairness Layer

**Purpose:** continuously monitor and mitigate algorithmic bias — with a clean separation between the serving path and the fairness evaluation path.

**Design (this fixes a coherence gap in v1, which fed anonymized data and protected attributes into the same call):**

```text
serving path:   state ──▶ [privacy redaction] ──▶ laya predict ──▶ decision
                                                        │
fairness path (separate, async):                        ▼
                decision log ──▶ join protected attributes (segregated store)
                              ──▶ parity / calibration-by-group metrics
                              ──▶ counterfactual probes (extra laya calls,
                                  never feed the primary decision)
```

**Metrics tracked:**
- Disparate impact ratio (80% rule) on `AUTO_DECIDE` rates by group
- Equal opportunity difference (true-positive rate parity)
- Demographic parity difference
- Calibration by group (ECE per group per question kind)
- Counterfactual flip rate: re-run `predict` with protected-attribute mentions substituted/redacted in the state; measure how often the selected option changes

**Honest caveat:** Laya consumes text. Protected attributes are handled at the privacy layer (redaction before serving) and evaluated in the fairness path on logged decisions. The fairness layer's counterfactual probes are a *measurement*, not a mitigation, and they cost one laya call each (~18–50 ms depending on context length).

### 4.3 Privacy Layer

**Purpose:** GDPR / HIPAA / CCPA compliance for data flowing through the platform.

**The architectural advantage of laya-mlx:** inference is local. No state, prompt, or probability leaves the machine — there is no third-party API to leak to. "Private by architecture" replaces v1's "encrypted API calls."

**Techniques:**
- **PII detection & redaction:** Microsoft Presidio, run before the state reaches the encoder. Redacted entities are replaced with typed placeholders (`[PERSON]`, `[EMAIL]`) so the model keeps the structure.
- **k-Anonymity:** enforced on anything exported from the audit/decision log for analysis.
- **Tokenization:** reversible tokens for fields that must round-trip (e.g., ticket IDs inside state).
- **Aggregation:** dashboards expose summary statistics only.

**Compliance checks:** GDPR Art. 25 (data protection by design — satisfied by local inference), GDPR Art. 22 (automated decision-making — satisfied by the REVIEW/ESCALATE policy router + explanation output), HIPAA Safe Harbor (Presidio + local processing), CCPA deletion (decision log rows keyed by subject token).

### 4.4 Explainability Layer

**Purpose:** auditable, human-readable explanations — without a text generator.

**Honest mechanism (v1 claimed the model "explains"; laya gives no free text, so ADIP assembles):**

1. **Contrastive summary (template):** "Routed to **billing** (p = 0.87) over **technical** (p = 0.09). Margin 0.78. Urgency score 1.4/2 (critical)." Assembled from the answer distributions by fixed templates per use case.
2. **Perturbation attribution (strict mode):** mutate one state field at a time, re-run `predict`, record the delta in the chosen option's probability. Each probe ≈ 18–50 ms depending on context length (measured anchors: 17.75 ms @ 1 short question, 49.84 ms @ full 512-token context); a bounded budget of 4–8 probes fits the strict-mode latency envelope. This is real, mechanistic feature attribution — not an LLM's post-hoc story.
3. **Counterfactuals (Section 4.5):** minimal state changes that flip the decision, with feasibility tiers.
4. **Compliance tags:** attached deterministically from the policy (e.g., GDPR_Art22 when `decision_type != AUTO_DECIDE`).

**Explanation schema:**

```typescript
interface Explanation {
  decision_id: string;
  explanation_type: "CONTRASTIVE" | "PERTURBATION" | "COUNTERFACTUAL";
  summary: string;                 // template-assembled, numbers from the distribution
  factors: Array<{                 // strict mode: perturbation attribution
    field: string;
    value: string;
    delta_probability: number;     // effect on the chosen option
    importance_rank: number;
  }>;
  counterfactuals: Array<{
    change: string;                // "set channel: email → phone"
    new_decision: string;
    feasibility: "EASY" | "MEDIUM" | "HARD";
    probability_after: number;
  }>;
  compliance_tags: string[];       // ["GDPR_Art22", "EU_AI_ACT_log"]
}
```

### 4.5 Counterfactual Engine

v1 hand-waved this ("Jev finds minimal changes"). With laya it is concretely implementable:

```text
for each mutable field f in state:
    for candidate value v of f (generated from field metadata + embed_fn similarity):
        state' = state with f = v
        p'     = predict(state', questions).answers[target].probability
        if decision_flips(p'): record (f, v, p')
rank candidates by edit distance and feasibility tier
```

- Candidate generation uses `laya.embed_fn_from_agent` mean-pooled embeddings (cosine similarity to plausible values) — no external vector DB needed.
- Probe budget is capped (e.g., 24 probes ≈ 0.4–1.2 s: 24 × 17.75 ms short-context to 24 × 49.84 ms full-context); interactive requests get a small inline budget (4–8 probes), full sweeps run as async background jobs.
- Output feeds both the explanation layer and an actionable "what would change this decision" report.

### 4.6 Monitoring & Drift

- **Serving metrics (Prometheus `/metrics`):** request rate, decision mix, latency histogram (P50/P95/P99 per stage), cache behavior.
- **Calibration monitor:** rolling ECE per question kind and per group. A rising ECE is the earliest "the model is drifting" signal available, and it is cheap to compute from logged probabilities.
- **Drift detection:** distribution shift in (a) answer distributions (JS divergence vs a pinned baseline window), (b) state embeddings (laya's own encoder embeddings, no extra model), (c) input language mix (the router's `detect_language` evidence is free telemetry).
- **Determinism watchdog:** nightly, run the 100-repeat determinism check from Section 9 on production hardware; any deviation fails the build.

### 4.7 Audit Layer

- Every decision writes an immutable row: inputs (hash of redacted state), questions, full distributions, policy version, checkpoint revision, dtype, latency, fairness flags.
- **Reproducibility:** pinned Hub revisions and weight checksums (the laya-mlx publication pipeline verifies all files against recorded hashes) mean any historical decision can be re-computed bit-for-bit on the same hardware.
- **Reports:** EU AI Act logging, GDPR Art. 22 review packets, internal fairness scorecards — generated from the audit DB, not from memory.

---

## 5. End-to-End Workflow Example: Support-Ticket Triage

The flagship use case is re-anchored on laya's demonstrated strength (text-state triage — the same domain as the upstream demo). The loan-approval example from v1 is **not** in-distribution for the pretrained checkpoints (Section 8, item 4) and is moved to Phase 2 as a fine-tuning stretch goal.

```python
async def process_ticket(ticket: Ticket) -> DecisionResponse:
    pipeline = DecisionPipeline()

    # === STAGE 1: Privacy scan (30–50 ms) — Presidio redaction ===
    privacy = await pipeline.privacy.scan(ticket.text)
    if privacy.hard_violation:
        return reject(reason="unredactable sensitive content", auto_redact=True)
    state = privacy.redacted_text

    # === STAGE 2: Fairness screen (10–20 ms) — rules + parity on live traffic ===
    fairness_flag = await pipeline.fairness.screen(state, decision_type="TRIAGE")
    # counterfactual probes here only in strict mode (+~18–50 ms each, capped)

    # === STAGE 3: Core decision (18–45 ms) — ONE batched laya call ===
    result = pipeline.laya.predict(state, TRIAGE_QUESTIONS)
    #   department: choice(billing | technical | sales | account)
    #   urgency:    score([not urgent, soon, critical])
    #   refund:     noul("Does the customer ask for money back?")

    # === STAGE 4: Policy router (<1 ms) — versioned thresholds ===
    decision = policy.route(result, fairness_flag=fairness_flag)

    # === STAGE 5: Explanation (5–10 ms) — template assembly from distributions ===
    explanation = pipeline.explain.contrastive(result, TRIAGE_QUESTIONS)

    # === STAGE 6: Audit + metrics (async, non-blocking) ===
    asyncio.create_task(pipeline.audit.log(state, result, decision))
    asyncio.create_task(pipeline.metrics.record(...))

    # === RETURN (~80–150 ms P50 standard mode; ~500 ms P50 strict mode, ≤ 1 s P95) ===
    return DecisionResponse(
        decision=decision,
        explanation=explanation,
        confidence=result.confidence,
        privacy_compliant=True,
        fairness_flag=fairness_flag,
    )
```

---

## 6. Technology Stack

Right-sized: everything below the "MVP" column is needed for the demo; the "Production" column is earned later, not assumed.

| Concern | MVP (Phase 0) | Production (Phase 2+) |
|---|---|---|
| Language / runtime | Python 3.11+, `uv` | same, pinned revisions |
| Decision model | `laya-mlx`, checkpoint `aac6fef/laya-mlx` (FP16) | + Router (multilingual), pinned revisions, float32 validation runs |
| API | FastAPI + uvicorn workers | + nginx LB across Mac nodes |
| Privacy | Microsoft Presidio (local) | + k-anonymity on exports |
| Storage | SQLite (WAL mode) | PostgreSQL 15+ |
| Metrics | Prometheus `/metrics` + Grafana | + alerting, drift jobs |
| Cache | in-process LRU keyed by `(sha256(state), sha256(questions))` | + shared Redis (optional) |
| CI | GitHub Actions `macos-14` arm64 runners | + nightly full-checkpoint benchmarks on hardware |
| Deployment | bare macOS processes + `launchd` keepalive | + multi-node LB, health checks |
| Vector / similarity | `laya.embed_fn_from_agent` (mean-pooled encoder) | + dedicated bi-encoder for shortlisting if needed |

**Removed from v1 (deliberately):** Apache Kafka, RabbitMQ, Istio, Pinecone/Weaviate, Kubernetes. At ADIP's actual workload (one ~18–45 ms in-process model call per decision) those components are complexity with no payoff. Laya's `predict_shortlist` replaces the vector-DB use case; SQLite→Postgres replaces the TSDB until metrics volume justifies more.

**Container caveat (important):** MLX needs native Metal access. Docker containers on macOS run inside a VM with no GPU passthrough, so **the inference service runs bare-metal on macOS** (venv/uv + `launchd`). Containers are fine only for stateless UIs.

---

## 7. Apple Silicon-First Deployment

**Hardware profile (per node):**

| Node | Chip | RAM | Resident model(s) | Realistic serving capacity |
|---|---|---|---|---|
| Dev / demo | M-series MacBook | 16–32 GB | 1 agent (≈0.9–1.0 GiB) | full pipeline, demo load |
| Serving node | Mac mini M4 Pro / M2 Max | 32–64 GB | 1–2 agents + pipeline | ~56 decisions/s/worker serial (17.75 ms/call, short context); ~110/s with 2 workers |
| Throughput node | M3 Max-class | 64–128 GB | 2–3 agents | 143.3 q/s (English) / 402.2 q/s (multilingual), FP16 batch-64, repeated-template fixture — not per-request serving |

**Process model:**
- One uvicorn worker per pinned agent. Worker count = `floor((RAM − 8 GB OS headroom) / 2 GiB)` (weights ≈ 0.8 GiB; peak allocation reaches 1.83 GiB with 10 full-context questions).
- `Router(preload=True)` when serving multiple languages from one process; the re-entrant lock shares loaded agents across threads safely (inference itself is not serialized).
- `launchd` keepalive + health endpoint; restart on OOM or load failure. No Kubernetes — there is nothing to orchestrate that `launchd` + nginx don't do better at this scale.

**Scaling out:** nginx → N Mac nodes, linear capacity, DNS or ALB in front. Failure mode is one node down; the LB drains it.

**Availability targets (honest):** 99.9% on a single node with auto-restart. 99.99% requires multi-node + LB — a Phase 3 goal, not an MVP claim.

**CI/CD:** GitHub Actions on `macos-14` arm64 runners runs the unit suite with small random models (no checkpoint download), mirroring laya-mlx's own CI. Full-checkpoint fidelity, calibration, and latency benchmarks run nightly on a real Mac and publish to the benchmark report.

---

## 8. Constraints & Honest Limitations

Each limitation, its consequence, and the mitigation ADIP adopts. This section exists because a decision platform that hides its failure modes is not auditable.

1. **Apple Silicon only.** MLX has no Linux/Windows build. Consequence: no commodity cloud CPU nodes, no GPU cloud. Mitigation: the deployment story is Mac hardware end to end; a cross-platform fallback would mean the upstream PyTorch runtime (2nd runtime to validate, explicitly deferred).
2. **No Docker GPU passthrough on macOS.** Consequence: no containerized inference. Mitigation: bare-metal `launchd` services; infra-as-code via scripts, not images.
3. **Context limit 512 tokens (English) / 1,024 (multilingual).** Consequence: the redacted state plus all question definitions must fit; long documents need chunking or summarization upstream. Mitigation: `state_token_estimate` guard in the output schema; use-case templates keep questions compact.
4. **The pretrained checkpoints are triage-style decision models.** They were not trained on credit risk or clinical outcomes. Consequence: v1's loan-approval flagship would silently underperform. Mitigation: flagship re-anchored on ticket triage; tabular/credit domains require fine-tuning via upstream RLCD on labeled data (Phase 2 stretch goal, gated on eval results).
5. **Confidence is not accuracy.** Upstream says it plainly; the calibrated probability is a property of the score distribution, not a promise. Mitigation: policy thresholds tuned on eval data, REVIEW band for low-margin cases, rolling ECE monitoring.
6. **Temperature clamping changes shipped probabilities.** laya-mlx clamps calibration temperatures to [0.5, 5.0] (the shipped `choice:11+` bucket would otherwise sharpen ~10×) and raises a `RuntimeWarning` per clamped bucket. Mitigation: surface the warnings in logs and model cards; never present raw-temperature outputs as calibrated.
7. **FP16 vs FP32 probabilities differ slightly** (selected labels usually agree). Consequence: a decision recomputed in a different dtype may land a hair from the threshold. Mitigation: pin `dtype` per environment; validation runs include a float32 pass; store dtype in every audit row.
8. **No free-text output at all.** Consequence: no generated rationales; users needing narrative explanations need a separate (audited) LLM stage. Mitigation: template + perturbation explanations (Section 4.4), and an explicit product boundary.
9. **Single-node throughput ceiling.** ~56 decisions/s per worker serial (one 17.75 ms call at short context); full-context requests cost 49.84 ms each. The 143.3 q/s figure applies to the 50-question repeated-template batch fixture, not per-request serving. v1's "10,000 decisions/second per cluster" is gone. Mitigation: scale by adding Mac nodes; batch large offline evaluation runs.
10. **Router heuristics can misroute language.** Unidentified Latin-script languages route to the multilingual checkpoint on diacritics alone. Mitigation: log `detect_language` evidence (`language_undecided`, `diacritic_rate`) with every decision; explicit `lang=`/`model=` overrides for known-critical flows.
11. **Prefix cache and compile are opt-in with caveats** (cache bounded to 128 questions; compilation has first-use cost and shape specialization; padding can slow some workloads). Mitigation: enable per workload only after measurement; the benchmark harness gates the decision.
12. **Independent port, not official.** laya-mlx is an Apache-2.0 MLX reimplementation validated against pinned upstream (378/378 fixture comparisons). Mitigation: pin revisions on both sides; run the fidelity harness (Section 9) as a CI gate.

---

## 9. Evaluation & Test Strategy

v1 had none. This mirrors the discipline of the laya-mlx repo itself (fidelity harness, determinism checks, stored timing samples).

**Golden dataset:** 200+ labeled support tickets (public support-triage datasets + hand-labeled set) with department labels, urgency rubric levels, and refund propositions. Frozen with a version tag; every eval run names its dataset version.

**Test tiers:**

| Tier | What | Where | Gate |
|---|---|---|---|
| Unit | small random models, schema round-trip, policy router, Presidio redaction | CI (macos-14 arm64), no checkpoint download | every PR |
| Fidelity | pin upstream `NandhaKishorM/laya` commit; compare sampled logits/probabilities against the reference path | nightly, real Mac | port fidelity 100% on our fixtures |
| Determinism | 100 repeated calls: identical probabilities, zero active-memory growth | nightly | 100/100 |
| Calibration | ECE (15 bins) + Brier per question kind, per dtype (FP16 and FP32) | nightly | ECE < 0.05 target; report clamped buckets |
| Accuracy | macro-F1, per-class precision/recall on the golden set | nightly | macro-F1 ≥ 0.85 target |
| Fairness | disparate impact ≥ 0.80; equal opportunity diff < 0.05; counterfactual flip rate reported | nightly | thresholds on `AUTO_DECIDE` rates |
| Latency | iterations=50, warmup=5, every timing sample stored (mirrors `benchmarks.run`) | nightly | decision-only P95 < 60 ms (3-question call); pipeline P95 < 400 ms |
| Regression | decision-flip rate vs pinned baseline checkpoint across the golden set | every checkpoint bump | < 2% unexplained flips |

**Benchmark hygiene (learned from the repo):** fresh process per backend/checkpoint, load time excluded, timing boundary documented (prompt prep + tokenization + tensors + synchronized inference + calibration + formatting), environment recorded. Reports live in versioned benchmark artifacts, not in prose claims.

---

## 10. Performance & Cost Model

**Latency (measured inputs, honest assembly):**

| Path | Composition | Target |
|---|---|---|
| Decision-only (laya call) | one batched `predict` | ≤ 45 ms P50 for a 3-question call (measured anchors: 17.75 ms @ 1q, 44.43 ms @ 5q, laya FP16, short context) |
| Pipeline, standard mode | privacy + screen + laya + policy + template explanation | ≤ 150 ms P50, ≤ 400 ms P95 |
| Pipeline, strict mode | + capped counterfactual/attribution probes (4–8 × ~18–50 ms) | ≤ 500 ms P50, ≤ 1,000 ms P95 |
| Offline eval (batch) | batch_size 16→64 | up to 143.3 q/s measured (repeated-template fixture) |

**Cost:**

| Item | v1 claim (Jev cloud) | v2 (laya-mlx local) |
|---|---|---|
| Marginal cost per decision | API tokens, $42/B tokens | **$0** |
| Hardware amortization | — | ≈ $0.000002/decision (a ~$2,000 Mac Studio / M3 Max-class node over 3 years ≈ 1.2 B decisions at ~56/s × 8 h × 250 business days/yr) |
| Data egress | state leaves the premises | **zero** — nothing leaves the machine |
| "200× cheaper than LLMs" | marketing claim | replaced by the numbers above |

---

## 11. Implementation Phases (End-Semester Realistic)

Team reality: 1–3 students / engineers. Phases below are scoped to that; the enterprise vision is preserved as uncommitted roadmap (Section 16).

### Phase 0 — MVP (Weeks 1–4, 1 engineer) — demo-able

| Week | Deliverable |
|---|---|
| 1 | Environment: `uv` project, `uv add laya-mlx`, download + pin `aac6fef/laya-mlx`; golden set v1 (50 tickets); `DecisionService` wrapper around `Agent.predict`; FastAPI `POST /decide` |
| 2 | Presidio privacy scan in front of the model; SQLite audit log (WAL); offline fairness metrics notebook (disparate impact, ECE) |
| 3 | Explanation assembler (contrastive templates); Prometheus `/metrics`; benchmark harness (stored samples, P50/P95) |
| 4 | Dashboard (Streamlit or single-page HTML); eval report; demo video; README + model card |

**MVP exit criteria:** pipeline P50 ≤ 150 ms on the demo Mac; macro-F1 ≥ 0.80 on golden set v1 (measured, published honestly); ECE reported per question kind; 10 fairness checks wired; audit log replayable (recompute any logged decision bit-for-bit).

### Phase 1 — Hardening (Weeks 5–10, 1–2 engineers)

Real-time fairness evaluation branch with counterfactual probes; counterfactual engine (Section 4.5); Postgres migration; CI gates from Section 9 enforced on PRs; multilingual Router integration with logged routing evidence; strict-mode latency budget validated.

### Phase 2 — Extension (Weeks 11–16, 2–4 engineers)

Second use case (document triage or lead scoring); fine-tuning exploration via upstream RLCD on domain-labeled data (gate: eval must beat the base checkpoint before any deployment); packaging (`pip install adip`); load testing on the serving-node profile; float32 validation pass.

### Phase 3 — Stretch (post-semester)

Multi-node fleet behind nginx; nightly fleet benchmarks; hosted-support offering experiments. **Explicitly NOT in scope and not promised:** SOC 2, FedRAMP, marketplace, no-code builder, 10k req/s clusters. These remain in the vision section as direction, not commitments.

---

## 12. Success Metrics & KPIs

| Metric | v1 claim (Jev) | v2 target (laya-mlx) |
|---|---|---|
| Decision-only latency | 70–500 ms | ≤ 45 ms P50 for a 3-question call (17.75 ms measured @ 1 short question) |
| Pipeline latency | < 500 ms | P50 ≤ 150 ms, P95 ≤ 400 ms (standard) |
| Throughput | 10,000+/s per cluster | 56–110 decisions/s per node; linear with nodes |
| Uptime | 99.99% | 99.9% single node (99.99% = Phase 3 multi-node) |
| Calibration error | < 5% | ECE < 0.05, reported per question kind and dtype |
| Accuracy | "> 90%" (unmeasured) | macro-F1 ≥ 0.85 on frozen golden set (measured in CI) |
| Fairness | "disparate impact > 0.8" | kept, plus equal-opportunity diff < 0.05 and counterfactual flip rate |
| Hallucinations | "zero" | constrained typed outputs; no free-text surface exists |
| Cost per decision | < $0.0001 | $0 marginal; ~$0.000002 amortized |
| Data egress | unspecified | zero (all local) |

---

## 13. Security & Compliance Framework

- **Auth:** OAuth 2.0 / OIDC on the API; RBAC for dashboards and audit exports. (ABAC deferred until there are real tenants.)
- **Data protection:** full-disk encryption (FileVault) on serving nodes; TLS 1.3 in transit; redaction at the front door; no third-party data processors in the serving path.
- **Audit:** immutable decision log; access to protected-attribute store is role-gated and itself audited; regular review of clamped-temperature warnings and router misroutes.
- **Supply chain:** pinned checkpoint revisions + weight checksums (verified at publication by the laya-mlx pipeline; verified at load by parameter-name/shape validation); `uv.lock` pinned dependencies.
- **Certifications:** out of scope for an end-semester project. Listed in the vision as future work only.

---

## 14. Documentation & Open-Source Strategy

- **Docs:** OpenAPI 3.0 from FastAPI; model card per checkpoint (following the published laya-mlx model cards: provenance, license, validation results, checksums); a "limits" page that restates Section 8 in product terms.
- **Open source:** release ADIP's fairness evaluation harness, explanation assembler, and policy router as an Apache-2.0 repo; upstream contributions (eval tooling, extra presets) where the laya maintainers want them.
- **Positioning:** ADIP is a self-hosted, privacy-first decision layer on open weights — the honest pitch is "fast, local, auditable," not "cheaper GPT."

---

## 15. Research & Open Questions

1. **Perturbation attribution quality:** how faithfully do one-field-at-a-time probability deltas approximate feature importance for a bidirectional encoder over concatenated state? (Baselines: occlusion over token spans; small linear probes on encoder embeddings.)
2. **Threshold calibration:** optimal AUTO/REVIEW/ESCALATE bands per use case, trading automation rate against review load, per Section 12 targets.
3. **Fine-tuning transfer:** can upstream RLCD adapt the 421M checkpoint to tabular-serialized domains (credit-style state) without losing calibration? Gate on the Section 9 harness.
4. **Embedding reuse:** `predict_shortlist` vs a dedicated bi-encoder for large option sets — accuracy and latency trade-offs on the golden set.
5. **Compile/prefix-cache payoff:** measured gain on the repo's Snake workload (~6.5%, README); validate before enabling in serving.

---

## 16. Future Roadmap (Vision, Non-Committing)

- **Multi-node fleets** of Mac serving nodes with shared eval infrastructure.
- **Domain checkpoints:** RLCD-fine-tuned variants per vertical, published with the same model-card + checksum discipline.
- **Hybrid runtime:** upstream PyTorch path for Linux shops — only if a real customer demands it (doubles the validation surface).
- **Simulation environment:** replay historical decision logs under candidate policies before rollout.
- **Policy versioning UI:** diff and A/B decision policies with automatic eval-gated promotion.

---

## 17. Immediate Next Steps

### Week 1 (concrete)
1. `uv init adip && uv add laya-mlx fastapi uvicorn presidio-analyzer prometheus-client`
2. Download and pin the checkpoint: `laya.load("aac6fef/laya-mlx")`; record the resolved Hub revision in `checkpoint.lock`.
3. Build the 50-ticket golden set v1; freeze with a version tag.
4. Wrap `Agent.predict` in `DecisionService` (token guard, dtype pin, error paths: load failure, OOM, context overflow).
5. FastAPI `POST /decide` returning the `DecisionOutput` schema; SQLite audit log.
6. CI: GitHub Actions `macos-14` arm64, unit tier only.

### Weeks 2–4
Follow the Phase 0 table (Section 11). Demo target: a ticket triaged end-to-end in < 150 ms P50 on a MacBook, with a replayable audit row and an honest eval report.

---

## 18. Attribution & Licensing

- **Laya** model and pretrained weights: Convai Innovations and upstream contributors (`NandhaKishorM/laya`).
- **laya-mlx**: independent Apache-2.0 MLX port (mizorewww); prompt construction, routing, presets adapted from upstream at pinned commit `573e5b6`. MLX is Apple's open-source array framework; ModernBERT/mmBERT encoders per their licenses.
- This document's runtime figures are quoted from the laya-mlx repo's checked-in `BENCHMARKS.md` (M3 Max, 40-core GPU, 128 GiB, macOS 27.2, Python 3.12.13, MLX 0.32.2; one machine, one run per configuration). Note: the laya-mlx README headline (13.42 / 7.39 ms) disagrees with its own BENCHMARKS.md (17.75 / 10.91 ms, MLX FP16, 1 short question) — this document follows BENCHMARKS.md. All figures must be re-measured on ADIP's own hardware before being quoted in any external material.

---

*Built for the era of typed decision models: fast, local, constrained, and honest about what it does not know.*
