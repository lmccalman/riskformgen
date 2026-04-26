"""One-off helper: generate the example-system registry fixture.

Run with `uv run python scripts/seed_example_registry.py`. Writes:

    registry/example-system/questionnaire.json
    registry/example-system/assessment.json
    registry/example-system/meta.yaml

Drives the real Alpine factories via the test harness so the produced
JSONs are guaranteed valid against the current form. Re-run if the form
changes and the fixture's IDs drift.

This script is not part of the build or the test suite — it's a developer
utility for refreshing the committed sample data.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

# Allow `uv run python scripts/seed_example_registry.py` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from build_id import compute_build_id
from parse import (
    load_controls,
    load_details,
    load_properties,
    load_risks,
    load_sections,
)
from tests.js_harness import build_assessment_scope

# Answers: a person who is desk-bound, drinks daily, eats poorly, stressed,
# socially connected, with family cardiac history but no chronic condition.
ANSWERS = {
    "q_is_active": "no",
    "q_exercises_often": "",
    "q_does_strength": "",
    "q_does_cardio": "",
    "q_desk_bound": "yes",
    "q_ergonomic_setup": "no",
    "q_balanced_meals": "no",
    "q_processed_food": "yes",
    "q_drinks_alcohol": "yes",
    "q_smokes_or_vapes": "no",
    "q_sleeps_well": "yes",
    "q_consistent_sleep": "yes",
    "q_feels_stress": "yes",
    "q_manages_stress": "no",
    "q_is_social": "yes",
    "q_feels_lonely": "no",
    "q_joins_groups": "no",
    "q_team_sports": "no",
    "q_outdoors_oriented": "no",
    "q_uses_sunscreen": "no",
    "q_sensitive_skin": "no",
    "q_chronic_condition": "no",
    "q_family_cardiac": "yes",
    "q_attends_checkups": "no",
}

DETAILS = {
    "substance_context": (
        "Two glasses of wine most evenings — about a bottle a week. No tobacco or vaping."
    ),
    "stress_context": (
        "Work has been heavy this quarter. I rely on friends and family to "
        "decompress but haven't been deliberate about stress management."
    ),
    "chronic_condition_context": "No diagnosed conditions.",
    "cardiac_history_context": "Father had a heart attack at 58.",
}

# Per-risk assessor judgement.
ASSESSMENT_INPUT: dict[str, dict[str, str]] = {
    "cardiovascular_risk": {
        "control_effectiveness": "partial",
        "residual_likelihood": "possible",
        "residual_consequence": "medium",
        "justification": (
            "Family history is unmodifiable, but moderating alcohol intake, "
            "addressing diet, and adding regular movement would meaningfully "
            "reduce likelihood. Mandating routine exercise and a checkup."
        ),
    },
    "metabolic_risk": {
        "control_effectiveness": "partial",
        "residual_likelihood": "possible",
        "residual_consequence": "medium",
        "justification": "Improvements to diet and movement would lower likelihood substantially.",
    },
    "mental_health_risk": {
        "control_effectiveness": "partial",
        "residual_likelihood": "possible",
        "residual_consequence": "medium",
        "justification": (
            "Person is socially connected and sleeps well, which compensates "
            "for chronic stress. A stress-management routine would reduce "
            "likelihood further."
        ),
    },
    "musculoskeletal_risk": {
        "control_effectiveness": "partial",
        "residual_likelihood": "unlikely",
        "residual_consequence": "medium",
        "justification": (
            "Ergonomic improvements and regular movement breaks would address most of this."
        ),
    },
    "substance_misuse_risk": {
        "control_effectiveness": "partial",
        "residual_likelihood": "possible",
        "residual_consequence": "medium",
        "justification": (
            "Daily but moderate use. Substituting some evenings for non-alcoholic "
            "alternatives is a reasonable mitigation."
        ),
    },
    "preventive_care_gap_risk": {
        "control_effectiveness": "ineffective",
        "residual_likelihood": "",
        "residual_consequence": "",
        "justification": "No preventive care happening — full inherent risk applies.",
    },
}

MANDATED_CONTROLS: dict[str, list[str]] = {
    "cardiovascular_risk": ["regular_exercise_routine", "regular_health_checkups"],
    "metabolic_risk": ["regular_exercise_routine", "nutrient_dense_diet"],
    "mental_health_risk": ["stress_management_practice"],
    "musculoskeletal_risk": ["ergonomic_workspace"],
}

MANDATED_COMMENTS: dict[str, dict[str, str]] = {
    "cardiovascular_risk": {
        "regular_exercise_routine": "Three sessions per week — mix of cardio and strength.",
        "regular_health_checkups": "Annual checkup with bloodwork given family history.",
    },
    "metabolic_risk": {
        "regular_exercise_routine": "Same as cardiovascular — joint mitigation.",
        "nutrient_dense_diet": (
            "Reduce processed-food intake; add a serving of vegetables to lunch and dinner."
        ),
    },
    "mental_health_risk": {
        "stress_management_practice": (
            "Try a structured practice — meditation app, journalling, or therapy."
        ),
    },
    "musculoskeletal_risk": {
        "ergonomic_workspace": (
            "Adjust chair, desk and screen height. Take a 5-minute break each hour."
        ),
    },
}


def _read_form() -> tuple[list, list, list, list, list]:
    details_path = config.form_dir / "details.yaml"
    details = load_details(details_path) if details_path.exists() else []
    details_by_id = {d.id: d for d in details}
    sections = load_sections(config.form_dir / "sections.yaml", details_by_id)
    properties = load_properties(config.form_dir / "properties.yaml")
    risks = load_risks(config.form_dir / "risks.yaml")
    controls = load_controls(config.form_dir / "controls.yaml")
    return sections, properties, risks, controls, details


def main() -> None:
    sections, properties, risks, controls, details = _read_form()
    build_id = compute_build_id(config.form_dir)
    scope = build_assessment_scope(sections, properties, risks, controls, details)

    for qid, ans in ANSWERS.items():
        scope.set_answer(qid, ans)
    for did, txt in DETAILS.items():
        scope.set_detail(did, txt)
    for rid, vals in ASSESSMENT_INPUT.items():
        scope.set_effectiveness(rid, vals["control_effectiveness"])
        if vals["residual_likelihood"] and vals["residual_consequence"]:
            scope.set_residual(rid, vals["residual_likelihood"], vals["residual_consequence"])
        scope.eval(f"scope.justifications['{rid}'] = {json.dumps(vals['justification'])};")
    for rid, ctrl_ids in MANDATED_CONTROLS.items():
        for cid in ctrl_ids:
            scope.eval(f"scope.mandated_controls['{rid}']['{cid}'] = true;")
    for rid, comments in MANDATED_COMMENTS.items():
        for cid, text in comments.items():
            scope.eval(f"scope.mandated_comments['{rid}']['{cid}'] = {json.dumps(text)};")

    # Read everything back out of the live scope to assemble exports.
    # mini-racer returns JS arrays/maps as native-ish wrappers; coerce to plain
    # Python so json.dumps can serialise them.
    def _py(value):
        if hasattr(value, "items"):
            return {k: _py(v) for k, v in value.items()}
        if hasattr(value, "__iter__") and not isinstance(value, str | bytes):
            return [_py(v) for v in value]
        return value

    question_ids: list[str] = list(scope.eval("scope._questionIds"))
    detail_ids: list[str] = list(scope.eval("scope._detailIds"))
    property_ids: list[str] = list(scope.eval("scope._propertyIds"))
    risk_ids: list[str] = list(scope.eval("scope._riskIds"))
    properties_state = {pid: scope.prop(pid) for pid in property_ids}
    answers_out = {qid: scope.eval(f"scope.answers['{qid}']") for qid in question_ids}
    details_out = {did: scope.eval(f"scope.details['{did}']") for did in detail_ids}

    inherent: dict[str, dict[str, object]] = {}
    risk_conditions: dict[str, list[str]] = _py(scope.eval("scope._riskConditions"))  # type: ignore[assignment]
    for rid in risk_ids:
        inh = scope.risk(rid)
        firing = [
            pid for pid in (risk_conditions.get(rid) or []) if properties_state.get(pid) is True
        ]
        inherent[rid] = {
            "likelihood": inh["likelihood"],
            "consequence": inh["consequence"],
            "level": inh["level"],
            "firing_conditions": firing,
        }

    timestamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    questionnaire_payload = {
        "format": config.QUESTIONNAIRE_FORMAT,
        "version": config.QUESTIONNAIRE_VERSION,
        "build_id": build_id,
        "exported_at": timestamp,
        "question_ids": question_ids,
        "answers": answers_out,
        "detail_ids": detail_ids,
        "details": details_out,
        "property_ids": property_ids,
        "properties": properties_state,
    }

    assessment_payload = {
        "format": config.ASSESSMENT_FORMAT,
        "version": config.ASSESSMENT_VERSION,
        "build_id": build_id,
        "exported_at": timestamp,
        "risk_ids": risk_ids,
        "property_ids": property_ids,
        "properties": properties_state,
        "inherent": inherent,
        "control_effectiveness": _py(scope.eval("scope.control_effectiveness")),
        "residual_likelihood": _py(scope.eval("scope.residual_likelihood")),
        "residual_consequence": _py(scope.eval("scope.residual_consequence")),
        "justifications": _py(scope.eval("scope.justifications")),
        "mandated_controls": _py(scope.eval("scope.mandated_controls")),
        "mandated_comments": _py(scope.eval("scope.mandated_comments")),
    }

    out_dir = Path(__file__).resolve().parent.parent / "registry" / "example-system"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "questionnaire.json").write_text(json.dumps(questionnaire_payload, indent=2) + "\n")
    (out_dir / "assessment.json").write_text(json.dumps(assessment_payload, indent=2) + "\n")

    meta = {
        "name": "Example System (demo data)",
        "owner": "Demo Owner",
        "notes": (
            "Sample fixture committed for documentation. Not a real assessment. "
            "Regenerate with `uv run python scripts/seed_example_registry.py`."
        ),
    }
    (out_dir / "meta.yaml").write_text(yaml.safe_dump(meta, sort_keys=False))

    print(f"Wrote example fixture to {out_dir}")


if __name__ == "__main__":
    main()
