"""Compute a structured diff between two committed (questionnaire, assessment) pairs.

Both the registry's per-system history view and the assessment view's live
diff overlay consume this same shape. The Python implementation here is
mirrored in the assessment Alpine factory's JS so live and server-rendered
diffs agree (parity is pinned by `tests/test_diff.py` running shared
fixtures through both paths).

The diff is a pure JSON-to-JSON computation: it takes the four committed
dicts and reports symbol-level differences. It does *not* know about the
form's structure — it does not consult `Control` / `Risk` model objects, it
does not re-run the property DAG. That's by design: the JSON exports
already bake in resolved property and inherent-risk state, and rendering
controls / risks against the current form is the renderer's job (and it
needs to handle form evolution edge cases that this layer cannot see).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ScalarChange:
    """A single keyed value that differs between two snapshots.

    `before` / `after` are `None` if the key is absent on that side
    (form-evolution case: id existed in only one of the two builds).
    """

    id: str
    before: Any
    after: Any


@dataclass(frozen=True)
class InherentBlock:
    likelihood: str | None
    consequence: str | None
    level: str
    firing_conditions: tuple[str, ...]


@dataclass(frozen=True)
class RiskChange:
    """Inherent block for a risk changed between snapshots.

    `before` or `after` may be `None` if the risk_id is absent on that side
    (form evolution). A risk whose inherent block is identical between the
    snapshots does not appear in `risk_changes`.
    """

    risk_id: str
    before: InherentBlock | None
    after: InherentBlock | None


@dataclass(frozen=True)
class ResidualChange:
    """Assessor inputs differ for a risk between snapshots.

    Each tuple is `(before, after)`. Empty string is the "unset" sentinel
    used by the assessment factory.
    """

    risk_id: str
    effectiveness: tuple[str, str]
    residual_likelihood: tuple[str, str]
    residual_consequence: tuple[str, str]
    justification: tuple[str, str]


@dataclass(frozen=True)
class MandateChange:
    """A specific (risk, control) mandate flag or its comment changed."""

    risk_id: str
    control_id: str
    mandated_before: bool
    mandated_after: bool
    comment_before: str
    comment_after: str


@dataclass(frozen=True)
class AggregateChange:
    level_before: str
    level_after: str
    justification_before: str
    justification_after: str


@dataclass(frozen=True)
class ChangeSummary:
    answer_changes: tuple[ScalarChange, ...] = ()
    detail_changes: tuple[ScalarChange, ...] = ()
    property_changes: tuple[ScalarChange, ...] = ()
    risk_changes: tuple[RiskChange, ...] = ()
    residual_changes: tuple[ResidualChange, ...] = ()
    mandate_changes: tuple[MandateChange, ...] = ()
    aggregate_change: AggregateChange | None = None
    prior_only_ids: dict[str, tuple[str, ...]] = field(default_factory=dict)
    current_only_ids: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return (
            not self.answer_changes
            and not self.detail_changes
            and not self.property_changes
            and not self.risk_changes
            and not self.residual_changes
            and not self.mandate_changes
            and self.aggregate_change is None
        )

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe form (tuples coerced to lists, used by registry + tests)."""
        return json.loads(json.dumps(asdict(self)))


# ---------------------------------------------------------------------------
# Per-section helpers
# ---------------------------------------------------------------------------


def _scalar_changes(prev: dict[str, Any], cur: dict[str, Any]) -> tuple[ScalarChange, ...]:
    """Diff two flat dicts. Stable order: keys sorted, missing values reported as None."""
    out: list[ScalarChange] = []
    for key in sorted(set(prev) | set(cur)):
        before = prev.get(key)
        after = cur.get(key)
        if before == after:
            continue
        out.append(ScalarChange(id=key, before=before, after=after))
    return tuple(out)


def _coerce_inherent(raw: Any) -> InherentBlock | None:
    if not isinstance(raw, dict):
        return None
    firing = raw.get("firing_conditions") or []
    return InherentBlock(
        likelihood=raw.get("likelihood"),
        consequence=raw.get("consequence"),
        level=str(raw.get("level", "not_applicable")),
        firing_conditions=tuple(firing),
    )


def _risk_changes(prev: dict[str, Any], cur: dict[str, Any]) -> tuple[RiskChange, ...]:
    out: list[RiskChange] = []
    for rid in sorted(set(prev) | set(cur)):
        before = _coerce_inherent(prev.get(rid))
        after = _coerce_inherent(cur.get(rid))
        if before == after:
            continue
        out.append(RiskChange(risk_id=rid, before=before, after=after))
    return tuple(out)


def _residual_changes(
    prev: dict[str, Any], cur: dict[str, Any], risk_ids: list[str]
) -> tuple[ResidualChange, ...]:
    """Per-risk diff over the four assessor-input fields.

    Treats the assessment dicts as a tuple of fields keyed by risk; emits
    a row only when at least one of the four fields differs.
    """
    out: list[ResidualChange] = []

    def _get(payload: dict[str, Any], field_name: str, rid: str) -> str:
        block = payload.get(field_name) or {}
        if not isinstance(block, dict):
            return ""
        val = block.get(rid, "")
        return str(val) if val is not None else ""

    for rid in risk_ids:
        eff_b = _get(prev, "control_effectiveness", rid)
        eff_a = _get(cur, "control_effectiveness", rid)
        rl_b = _get(prev, "residual_likelihood", rid)
        rl_a = _get(cur, "residual_likelihood", rid)
        rc_b = _get(prev, "residual_consequence", rid)
        rc_a = _get(cur, "residual_consequence", rid)
        just_b = _get(prev, "justifications", rid)
        just_a = _get(cur, "justifications", rid)
        if eff_b == eff_a and rl_b == rl_a and rc_b == rc_a and just_b == just_a:
            continue
        out.append(
            ResidualChange(
                risk_id=rid,
                effectiveness=(eff_b, eff_a),
                residual_likelihood=(rl_b, rl_a),
                residual_consequence=(rc_b, rc_a),
                justification=(just_b, just_a),
            )
        )
    return tuple(out)


def _mandate_changes(prev: dict[str, Any], cur: dict[str, Any]) -> tuple[MandateChange, ...]:
    """Per (risk, control) diff over mandated flag and its comment.

    Walks the union of (risk_id, control_id) pairs across both
    `mandated_controls` and `mandated_comments` blocks on both sides.
    """

    def _safe_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
        block = payload.get(key)
        return block if isinstance(block, dict) else {}

    prev_mandated = _safe_dict(prev, "mandated_controls")
    cur_mandated = _safe_dict(cur, "mandated_controls")
    prev_comments = _safe_dict(prev, "mandated_comments")
    cur_comments = _safe_dict(cur, "mandated_comments")

    def _lookup(block: dict[str, Any], rid: str, cid: str, default: Any) -> Any:
        sub = block.get(rid)
        if not isinstance(sub, dict):
            return default
        return sub.get(cid, default)

    pairs: set[tuple[str, str]] = set()
    for block in (prev_mandated, cur_mandated, prev_comments, cur_comments):
        for rid, controls in block.items():
            if not isinstance(controls, dict):
                continue
            for cid in controls:
                pairs.add((rid, cid))

    out: list[MandateChange] = []
    for rid, cid in sorted(pairs):
        m_before = bool(_lookup(prev_mandated, rid, cid, False))
        m_after = bool(_lookup(cur_mandated, rid, cid, False))
        c_before = str(_lookup(prev_comments, rid, cid, "") or "")
        c_after = str(_lookup(cur_comments, rid, cid, "") or "")
        if m_before == m_after and c_before == c_after:
            continue
        out.append(
            MandateChange(
                risk_id=rid,
                control_id=cid,
                mandated_before=m_before,
                mandated_after=m_after,
                comment_before=c_before,
                comment_after=c_after,
            )
        )
    return tuple(out)


def _aggregate_change(prev: dict[str, Any], cur: dict[str, Any]) -> AggregateChange | None:
    lvl_b = str(prev.get("aggregate_residual_level", "") or "")
    lvl_a = str(cur.get("aggregate_residual_level", "") or "")
    just_b = str(prev.get("aggregate_residual_justification", "") or "")
    just_a = str(cur.get("aggregate_residual_justification", "") or "")
    if lvl_b == lvl_a and just_b == just_a:
        return None
    return AggregateChange(
        level_before=lvl_b,
        level_after=lvl_a,
        justification_before=just_b,
        justification_after=just_a,
    )


def _id_set(payload: dict[str, Any], key: str) -> set[str]:
    raw = payload.get(key) or []
    return {str(x) for x in raw if isinstance(x, str)}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def diff_pair(
    prev_questionnaire: dict[str, Any] | None,
    prev_assessment: dict[str, Any] | None,
    cur_questionnaire: dict[str, Any],
    cur_assessment: dict[str, Any] | None,
) -> ChangeSummary:
    """Compare two pairs of committed JSONs.

    `prev_*` may be `None` when there is nothing to compare against (the
    first record in a system's history). In that case the returned
    `ChangeSummary` reports every current id as "new" via
    `current_only_ids` and leaves every change list empty.
    """
    if prev_questionnaire is None:
        return ChangeSummary(
            current_only_ids={
                "questions": tuple(sorted(_id_set(cur_questionnaire, "question_ids"))),
                "details": tuple(sorted(_id_set(cur_questionnaire, "detail_ids"))),
                "properties": tuple(sorted(_id_set(cur_questionnaire, "property_ids"))),
                "risks": tuple(sorted(_id_set(cur_assessment or {}, "risk_ids"))),
            }
        )

    prev_q = prev_questionnaire
    cur_q = cur_questionnaire
    prev_a = prev_assessment or {}
    cur_a = cur_assessment or {}

    prev_q_ids = _id_set(prev_q, "question_ids")
    cur_q_ids = _id_set(cur_q, "question_ids")
    prev_d_ids = _id_set(prev_q, "detail_ids")
    cur_d_ids = _id_set(cur_q, "detail_ids")
    prev_p_ids = _id_set(prev_q, "property_ids")
    cur_p_ids = _id_set(cur_q, "property_ids")
    prev_r_ids = _id_set(prev_a, "risk_ids")
    cur_r_ids = _id_set(cur_a, "risk_ids")

    prev_only = {
        "questions": tuple(sorted(prev_q_ids - cur_q_ids)),
        "details": tuple(sorted(prev_d_ids - cur_d_ids)),
        "properties": tuple(sorted(prev_p_ids - cur_p_ids)),
        "risks": tuple(sorted(prev_r_ids - cur_r_ids)),
    }
    current_only = {
        "questions": tuple(sorted(cur_q_ids - prev_q_ids)),
        "details": tuple(sorted(cur_d_ids - prev_d_ids)),
        "properties": tuple(sorted(cur_p_ids - prev_p_ids)),
        "risks": tuple(sorted(cur_r_ids - prev_r_ids)),
    }

    # Residual calls are only meaningful for risks present in the current
    # assessment — a removed risk's prior residual is captured by the
    # risk_change row (before=block, after=None) and adds noise here.
    return ChangeSummary(
        answer_changes=_scalar_changes(prev_q.get("answers") or {}, cur_q.get("answers") or {}),
        detail_changes=_scalar_changes(prev_q.get("details") or {}, cur_q.get("details") or {}),
        property_changes=_scalar_changes(
            prev_q.get("properties") or {}, cur_q.get("properties") or {}
        ),
        risk_changes=_risk_changes(prev_a.get("inherent") or {}, cur_a.get("inherent") or {}),
        residual_changes=_residual_changes(prev_a, cur_a, sorted(cur_r_ids)),
        mandate_changes=_mandate_changes(prev_a, cur_a),
        aggregate_change=_aggregate_change(prev_a, cur_a),
        prior_only_ids={k: v for k, v in prev_only.items() if v},
        current_only_ids={k: v for k, v in current_only.items() if v},
    )
