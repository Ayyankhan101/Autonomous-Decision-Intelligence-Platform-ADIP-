"""ADIP shared kernel: one definition each for the question payload, thresholds,
and metric math that the serving pipeline, eval runner, benchmark harness, and
dataset tooling must not silently drift apart on."""

__all__ = ["config", "questions", "stats"]
