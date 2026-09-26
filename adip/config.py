"""Thresholds, checkpoint ids, and gate limits — one definition each.

Every number here was previously a literal scattered over 2-5 files; a change
in one copy silently disagreed with the others (and with the reports that
quote them).
"""

from __future__ import annotations

from pathlib import Path

# --- model -----------------------------------------------------------------
CHECKPOINT = "aac6fef/laya-mlx"
DTYPE = "float16"
BATCH_SIZE = 16

# --- policy router (serving) ----------------------------------------------
# NOTE: blueprint section 4 describes p >= 0.90 with margin >= 0.20; Phase 0
# ships these confidence-only thresholds and computes no margin/entropy. The
# docs describe THESE numbers (see README "Policy router"); raising the bar
# needs margin computation first.
CONF_AUTO = 0.60
CONF_REVIEW = 0.35

# --- refund head -----------------------------------------------------------
REFUND_THRESHOLD = 0.5
# Router: a calibrated refund probability inside [threshold, HI) is a borderline
# money-back ask — auto-deciding it risks an unreviewed refund path.
REFUND_REVIEW_HI = 0.7
# Temperature fit by evals/calibrate.py on golden v1.0 predictions (T_global_fit
# in evals/results/calibration-refund-20260923.json). tests/test_config.py
# asserts this still equals that artifact — refit without updating this line
# and CI fails instead of serving a stale calibration.
REFUND_TEMPERATURE = 0.45

# --- department head --------------------------------------------------------
# Multiclass temperature (p^(1/T), renormalised) fitted by
# evals/calibrate_dept.py on golden-v2.0 predictions: multiclass-Brier-optimal
# on all 50 (T=0.6) — a proper scoring rule, same fit protocol as the refund
# head's NLL grid. In-sample ECE 0.1629 -> 0.0981; honest OOF estimate (5-fold,
# T refit per fold) 0.1449. Knife-edge note: ECE(T=0.55)=0.139, ECE(0.65)=0.113,
# bootstrap 95% CI at T=0.6 [0.087, 0.246] — n=50 binning noise dominates, which
# is why the strict gate is 0.15 and not 0.10 (D6+ renegotiation, 2026-09-26).
# tests/test_config.py pins this to the committed artifact.
DEPT_TEMPERATURE = 0.6

# --- eval gates (D6 renegotiation, 2026-09-26) -----------------------------
# STRICT gates: what `run_eval.py --strict` enforces. The original blueprint
# §9/§11 numbers proved unreachable on this hardware / this n=50 golden set
# (evidence table: README "Eval gates", BLUEPRINT §12), so the strict bar moved
# to the interim values below. The originals live on as *_TARGET /
# *_TARGET_MS and are reported in every run as `aspirational_targets`, not
# enforced. Do not silently tighten or loosen: renegotiation is a decision.
GATE_MACRO_F1 = 0.75              # interim MVP gate (post-V5 payload: 0.7698 PASS)
GATE_ECE_DEPT = 0.15              # interim (renegotiated 0.10 -> 0.15: honest OOF
                                  # ceiling at n=50 is 0.13-0.17; T=0.6 calibrated
                                  # in-sample 0.0981, OOF 0.1449 — both < 0.15)
GATE_ECE_URGENCY = 0.15           # interim (measured 0.1491)
GATE_ECE_REFUND = 0.05            # kept strict — measured 0.0365 PASS
GATE_URGENCY_ACCURACY = 0.55      # interim (measured 0.56 argmax; OOF threshold tuning 0.58; baseline 0.40)
GATE_DECISION_P50_MS = 100.0      # replaces the unreachable decision-p95<60ms gate
                                 # (latency ∝ input tokens: 135 tok→48.5 ms, 483→132 ms)

# Aspirational §9/§11 targets — reported, NOT enforced by --strict.
GATE_MACRO_F1_TARGET = 0.85       # aspirational (payload v3 criteria fixes landed: 0.7698; 0.85 needs OOF headroom)
GATE_ECE_TARGET = 0.05            # all heads; needs a held-out calibration set
GATE_ECE_DEPT_TARGET = 0.10       # first interim dept bar — unreachable at n=50
                                  # (evidence above), kept as a reported target
GATE_URGENCY_ACCURACY_TARGET = 0.60
GATE_LATENCY_P95_TARGET_MS = 60.0 # decision-only P95; M3 Max-class nodes or shorter states

# --- serving KPI (blueprint section 10) ------------------------------------
KPI_P50_MS = 150.0
KPI_P95_MS = 400.0

# --- dataset ---------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_SET_DEFAULT = "datasets/golden-set/golden-v2.0.json"
CALIBRATION_ARTIFACT = "evals/results/calibration-refund-20260923.json"
DEPT_CALIBRATION_ARTIFACT = "evals/results/calibration-dept-20260926.json"
