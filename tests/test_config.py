"""Tests for config.py — risk matrix completeness and scale sanity."""

from __future__ import annotations

from config import CONSEQUENCES, LIKELIHOODS, RISK_LEVELS, RISK_MATRIX


class TestRiskMatrix:
    def test_covers_all_likelihood_consequence_pairs(self):
        for lik in LIKELIHOODS:
            for con in CONSEQUENCES:
                assert lik in RISK_MATRIX, f"Missing likelihood key: {lik}"
                assert con in RISK_MATRIX[lik], (
                    f"Missing consequence {con!r} for likelihood {lik!r}"
                )

    def test_all_values_are_valid_risk_levels(self):
        for lik, row in RISK_MATRIX.items():
            for con, level in row.items():
                assert level in RISK_LEVELS, f"Invalid risk level {level!r} at ({lik}, {con})"

    def test_scales_are_nonempty_tuples(self):
        for name, scale in [
            ("LIKELIHOODS", LIKELIHOODS),
            ("CONSEQUENCES", CONSEQUENCES),
            ("RISK_LEVELS", RISK_LEVELS),
        ]:
            assert isinstance(scale, tuple), f"{name} should be a tuple"
            assert len(scale) > 0, f"{name} should not be empty"
            assert all(isinstance(s, str) for s in scale), f"{name} entries should be strings"
