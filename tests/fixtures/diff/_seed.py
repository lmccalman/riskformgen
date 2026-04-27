"""One-off helper to materialise the diff fixture corpus.

Run with `uv run python tests/fixtures/diff/_seed.py`. Writes one
subfolder per scenario under `tests/fixtures/diff/`. The fixtures are
checked in; the seed is only used to regenerate them after changing
either the diff shape or the canonical inputs (and to keep the JSON
formatting consistent — `json.dumps(..., indent=2, sort_keys=True)`).

The scenarios are deliberately small and orthogonal: each isolates one
kind of change so a failing assertion points unambiguously at what
regressed. The "kitchen_sink" scenario combines several to guard against
list-ordering / aggregation bugs that single-change cases miss.
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

# Allow running from the repo root via `uv run python tests/fixtures/diff/_seed.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from diff import diff_pair

_HERE = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Canonical templates
# ---------------------------------------------------------------------------

BASE_QUESTIONNAIRE: dict = {
    "format": "riskformgen-answers",
    "version": 2,
    "build_id": "abcd1234",
    "exported_at": "2026-01-15T10:00:00Z",
    "question_ids": ["q1", "q2", "q3"],
    "answers": {"q1": "yes", "q2": "no", "q3": ""},
    "detail_ids": ["d1"],
    "details": {"d1": "prior note"},
    "property_ids": ["p1", "p2"],
    "properties": {"p1": True, "p2": False},
}

BASE_ASSESSMENT: dict = {
    "format": "riskformgen-assessment",
    "version": 4,
    "build_id": "abcd1234",
    "exported_at": "2026-01-15T11:00:00Z",
    "questionnaire_exported_at": "2026-01-15T10:00:00Z",
    "risk_ids": ["r1", "r2"],
    "property_ids": ["p1", "p2"],
    "properties": {"p1": True, "p2": False},
    "inherent": {
        "r1": {
            "likelihood": "likely",
            "consequence": "major",
            "level": "high",
            "firing_conditions": ["p1"],
        },
        "r2": {
            "likelihood": None,
            "consequence": None,
            "level": "not_applicable",
            "firing_conditions": [],
        },
    },
    "control_effectiveness": {"r1": "ineffective", "r2": ""},
    "residual_likelihood": {"r1": "", "r2": ""},
    "residual_consequence": {"r1": "", "r2": ""},
    "justifications": {"r1": "Initial call.", "r2": ""},
    "mandated_controls": {"r1": {"c1": False}, "r2": {}},
    "mandated_comments": {"r1": {"c1": ""}, "r2": {}},
    "aggregate_residual_level": "",
    "aggregate_residual_justification": "",
}


def _scenario(name: str, prev_q, prev_a, cur_q, cur_a) -> None:
    folder = _HERE / name
    folder.mkdir(exist_ok=True)
    if prev_q is not None:
        (folder / "prev_q.json").write_text(_dump(prev_q))
    if prev_a is not None:
        (folder / "prev_a.json").write_text(_dump(prev_a))
    (folder / "cur_q.json").write_text(_dump(cur_q))
    if cur_a is not None:
        (folder / "cur_a.json").write_text(_dump(cur_a))
    summary = diff_pair(prev_q, prev_a, cur_q, cur_a)
    (folder / "expected.json").write_text(_dump(summary.to_dict()))


def _dump(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def main() -> None:
    # --- no_change: identical pairs → empty summary ---
    prev_q = deepcopy(BASE_QUESTIONNAIRE)
    prev_a = deepcopy(BASE_ASSESSMENT)
    _scenario("no_change", prev_q, prev_a, deepcopy(prev_q), deepcopy(prev_a))

    # --- answer_flip: q2 yes → no, p2 flips false → true, q3 picks up text ---
    prev_q = deepcopy(BASE_QUESTIONNAIRE)
    prev_a = deepcopy(BASE_ASSESSMENT)
    cur_q = deepcopy(prev_q)
    cur_q["exported_at"] = "2026-04-01T10:00:00Z"
    cur_q["answers"]["q2"] = "yes"
    cur_q["answers"]["q3"] = "yes"
    cur_q["properties"]["p2"] = True
    cur_q["details"]["d1"] = "updated note"
    cur_a = deepcopy(prev_a)
    cur_a["exported_at"] = "2026-04-01T11:00:00Z"
    cur_a["questionnaire_exported_at"] = "2026-04-01T10:00:00Z"
    cur_a["properties"] = deepcopy(cur_q["properties"])
    _scenario("answer_flip", prev_q, prev_a, cur_q, cur_a)

    # --- risk_inherent_changed: r1's firing conditions and level shift ---
    prev_q = deepcopy(BASE_QUESTIONNAIRE)
    prev_a = deepcopy(BASE_ASSESSMENT)
    cur_q = deepcopy(prev_q)
    cur_q["answers"]["q1"] = "no"
    cur_q["properties"]["p1"] = False
    cur_a = deepcopy(prev_a)
    cur_a["properties"] = deepcopy(cur_q["properties"])
    cur_a["inherent"]["r1"] = {
        "likelihood": None,
        "consequence": None,
        "level": "not_applicable",
        "firing_conditions": [],
    }
    _scenario("risk_inherent_changed", prev_q, prev_a, cur_q, cur_a)

    # --- residual_call_changed: assessor flipped effectiveness + filled L/C ---
    prev_q = deepcopy(BASE_QUESTIONNAIRE)
    prev_a = deepcopy(BASE_ASSESSMENT)
    cur_q = deepcopy(prev_q)
    cur_a = deepcopy(prev_a)
    cur_a["control_effectiveness"]["r1"] = "partial"
    cur_a["residual_likelihood"]["r1"] = "possible"
    cur_a["residual_consequence"]["r1"] = "medium"
    cur_a["justifications"]["r1"] = "Partial mitigation in place."
    _scenario("residual_call_changed", prev_q, prev_a, cur_q, cur_a)

    # --- mandate_added: c1 becomes mandated with comment ---
    prev_q = deepcopy(BASE_QUESTIONNAIRE)
    prev_a = deepcopy(BASE_ASSESSMENT)
    cur_q = deepcopy(prev_q)
    cur_a = deepcopy(prev_a)
    cur_a["mandated_controls"]["r1"]["c1"] = True
    cur_a["mandated_comments"]["r1"]["c1"] = "Implement before next review."
    _scenario("mandate_added", prev_q, prev_a, cur_q, cur_a)

    # --- aggregate_changed: assessor set an explicit aggregate level ---
    prev_q = deepcopy(BASE_QUESTIONNAIRE)
    prev_a = deepcopy(BASE_ASSESSMENT)
    cur_q = deepcopy(prev_q)
    cur_a = deepcopy(prev_a)
    cur_a["aggregate_residual_level"] = "medium"
    cur_a["aggregate_residual_justification"] = "Net medium after controls."
    _scenario("aggregate_changed", prev_q, prev_a, cur_q, cur_a)

    # --- form_evolution: prior had q_old/p_old/r_old; current has q_new/p_new/r_new ---
    prev_q = deepcopy(BASE_QUESTIONNAIRE)
    prev_q["question_ids"] = ["q1", "q_old"]
    prev_q["answers"] = {"q1": "yes", "q_old": "yes"}
    prev_q["property_ids"] = ["p1", "p_old"]
    prev_q["properties"] = {"p1": True, "p_old": True}
    prev_a = deepcopy(BASE_ASSESSMENT)
    prev_a["risk_ids"] = ["r1", "r_old"]
    prev_a["properties"] = deepcopy(prev_q["properties"])
    prev_a["inherent"] = {
        "r1": deepcopy(BASE_ASSESSMENT["inherent"]["r1"]),
        "r_old": {
            "likelihood": "rare",
            "consequence": "minor",
            "level": "low",
            "firing_conditions": ["p_old"],
        },
    }
    prev_a["control_effectiveness"] = {"r1": "ineffective", "r_old": "ineffective"}
    prev_a["residual_likelihood"] = {"r1": "", "r_old": ""}
    prev_a["residual_consequence"] = {"r1": "", "r_old": ""}
    prev_a["justifications"] = {"r1": "Initial call.", "r_old": "Legacy."}
    prev_a["mandated_controls"] = {"r1": {"c1": False}, "r_old": {}}
    prev_a["mandated_comments"] = {"r1": {"c1": ""}, "r_old": {}}
    cur_q = deepcopy(BASE_QUESTIONNAIRE)
    cur_q["question_ids"] = ["q1", "q_new"]
    cur_q["answers"] = {"q1": "yes", "q_new": "yes"}
    cur_q["property_ids"] = ["p1", "p_new"]
    cur_q["properties"] = {"p1": True, "p_new": True}
    cur_a = deepcopy(BASE_ASSESSMENT)
    cur_a["risk_ids"] = ["r1", "r_new"]
    cur_a["properties"] = deepcopy(cur_q["properties"])
    cur_a["inherent"] = {
        "r1": deepcopy(BASE_ASSESSMENT["inherent"]["r1"]),
        "r_new": {
            "likelihood": "possible",
            "consequence": "medium",
            "level": "medium",
            "firing_conditions": ["p_new"],
        },
    }
    cur_a["control_effectiveness"] = {"r1": "ineffective", "r_new": ""}
    cur_a["residual_likelihood"] = {"r1": "", "r_new": ""}
    cur_a["residual_consequence"] = {"r1": "", "r_new": ""}
    cur_a["justifications"] = {"r1": "Initial call.", "r_new": ""}
    cur_a["mandated_controls"] = {"r1": {"c1": False}, "r_new": {}}
    cur_a["mandated_comments"] = {"r1": {"c1": ""}, "r_new": {}}
    _scenario("form_evolution", prev_q, prev_a, cur_q, cur_a)

    # --- first_record: no prior at all → current_only_ids populated ---
    cur_q = deepcopy(BASE_QUESTIONNAIRE)
    cur_a = deepcopy(BASE_ASSESSMENT)
    _scenario("first_record", None, None, cur_q, cur_a)

    # --- kitchen_sink: every kind of change at once ---
    prev_q = deepcopy(BASE_QUESTIONNAIRE)
    prev_a = deepcopy(BASE_ASSESSMENT)
    cur_q = deepcopy(prev_q)
    cur_q["exported_at"] = "2026-04-01T10:00:00Z"
    cur_q["answers"]["q1"] = "no"
    cur_q["answers"]["q3"] = "yes"
    cur_q["details"]["d1"] = "updated note"
    cur_q["properties"]["p1"] = False
    cur_a = deepcopy(prev_a)
    cur_a["exported_at"] = "2026-04-01T11:00:00Z"
    cur_a["questionnaire_exported_at"] = "2026-04-01T10:00:00Z"
    cur_a["properties"] = deepcopy(cur_q["properties"])
    cur_a["inherent"]["r1"] = {
        "likelihood": None,
        "consequence": None,
        "level": "not_applicable",
        "firing_conditions": [],
    }
    cur_a["control_effectiveness"]["r1"] = "controlled"
    cur_a["justifications"]["r1"] = "Risk no longer applicable."
    cur_a["mandated_controls"]["r1"]["c1"] = True
    cur_a["mandated_comments"]["r1"]["c1"] = "Mandated last cycle."
    cur_a["aggregate_residual_level"] = "low"
    cur_a["aggregate_residual_justification"] = "Net low after this cycle."
    _scenario("kitchen_sink", prev_q, prev_a, cur_q, cur_a)


if __name__ == "__main__":
    main()
