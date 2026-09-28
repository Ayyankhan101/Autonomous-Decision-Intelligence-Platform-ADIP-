"""Deterministic seeding (plan Phase 1): fixed seed reproduces event order, attributes,
bad-data injection, resource states, and second-emergency timing."""
from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class SeedConfig:
    session_seed: int = 42
    scenario_seed: int = 7


def build_rngs(config: SeedConfig) -> tuple[random.Random, random.Random]:
    session_rng = random.Random(config.session_seed)
    scenario_rng = random.Random(config.session_seed * 1_000_003 + config.scenario_seed)
    return session_rng, scenario_rng
