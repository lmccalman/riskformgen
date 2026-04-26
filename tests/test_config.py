"""Tests for config.py — risk matrix completeness and scale sanity."""

from __future__ import annotations

from config import CONSEQUENCES, LIKELIHOODS, RISK_LEVEL_COLOURS, RISK_LEVELS, RISK_MATRIX


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

    def test_no_sentinel_levels_in_matrix(self):
        """SPEC §Risks: 'Two distinguished risk levels do not appear in the
        matrix' (`not_applicable` and `controlled`). They are reached only via
        the no-condition-fires path and the residual-controlled path."""
        forbidden = {"not_applicable", "controlled"}
        for lik, row in RISK_MATRIX.items():
            for con, level in row.items():
                assert level not in forbidden, (
                    f"Sentinel level {level!r} must not appear in matrix "
                    f"(at likelihood={lik!r}, consequence={con!r})"
                )

    def test_matrix_monotonic_with_scales(self):
        """Severity in `RISK_LEVELS` must be monotonic with `LIKELIHOODS` and
        `CONSEQUENCES` index. Increasing one axis (holding the other fixed)
        must not decrease the matrix's resolved risk-level index. Pins the
        ordering convention documented in config.py ("order = ascending
        severity")."""
        for con in CONSEQUENCES:
            indices = [RISK_LEVELS.index(RISK_MATRIX[lik][con]) for lik in LIKELIHOODS]
            assert indices == sorted(indices), (
                f"Matrix not monotonic in likelihood at consequence={con!r}: "
                f"levels are {[RISK_MATRIX[lik][con] for lik in LIKELIHOODS]}"
            )
        for lik in LIKELIHOODS:
            indices = [RISK_LEVELS.index(RISK_MATRIX[lik][con]) for con in CONSEQUENCES]
            assert indices == sorted(indices), (
                f"Matrix not monotonic in consequence at likelihood={lik!r}: "
                f"levels are {[RISK_MATRIX[lik][con] for con in CONSEQUENCES]}"
            )

    def test_scales_are_nonempty_tuples(self):
        for name, scale in [
            ("LIKELIHOODS", LIKELIHOODS),
            ("CONSEQUENCES", CONSEQUENCES),
            ("RISK_LEVELS", RISK_LEVELS),
        ]:
            assert isinstance(scale, tuple), f"{name} should be a tuple"
            assert len(scale) > 0, f"{name} should not be empty"
            assert all(isinstance(s, str) for s in scale), f"{name} entries should be strings"

    def test_sentinel_levels_present(self):
        """`not_applicable` and `controlled` must exist in `RISK_LEVELS` even
        though they're out-of-matrix — JS code paths and templates rely on
        them as named values."""
        assert "not_applicable" in RISK_LEVELS
        assert "controlled" in RISK_LEVELS


class TestRiskLevelColours:
    def test_covers_all_levels(self):
        """Every level in `RISK_LEVELS` must have a colour entry. A missing
        colour fails silently in templates (Bulma classes interpolated against
        an undefined value)."""
        missing = [level for level in RISK_LEVELS if level not in RISK_LEVEL_COLOURS]
        assert not missing, f"RISK_LEVEL_COLOURS missing entries: {missing}"

    def test_no_extraneous_colours(self):
        """Colour map should not declare entries for levels that don't exist
        — likely a typo or stale level."""
        extra = [level for level in RISK_LEVEL_COLOURS if level not in RISK_LEVELS]
        assert not extra, f"RISK_LEVEL_COLOURS has stale entries: {extra}"
