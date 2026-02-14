import json
from dataclasses import fields

from jinja2 import Environment, FileSystemLoader, select_autoescape

import config
from models import Control, Question, Risk, Section, SubSection, all_questions


def create_environment() -> Environment:
    """Create a Jinja2 environment loading from the templates directory."""
    return Environment(
        loader=FileSystemLoader(config.templates_dir),
        autoescape=select_autoescape(default=True),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _prepare_question(q: Question) -> dict:
    """Convert a Question dataclass to a template-ready dict with compiled visibility JS."""
    d = {f.name: getattr(q, f.name) for f in fields(q) if f.name != "visible_when"}
    if q.visible_when is not None:
        d["visible_when_js"] = q.visible_when.to_js()
    return d


def _prepare_subsection(sub: SubSection) -> dict:
    """Convert a SubSection to a template-ready dict with compiled visibility JS."""
    d = {
        "title": sub.title,
        "description": sub.description,
        "questions": [_prepare_question(q) for q in sub.questions],
    }
    if sub.visible_when is not None:
        d["visible_when_js"] = sub.visible_when.to_js()
    return d


def prepare_sections(sections: list[Section]) -> list[dict]:
    """Convert Section dataclasses to template-ready nested dicts."""
    return [
        {
            "id": section.id,
            "title": section.title,
            "description": section.description,
            "subsections": [_prepare_subsection(sub) for sub in section.subsections],
        }
        for section in sections
    ]


def prepare_risks(risks: list[Risk], questions: list[Question]) -> list[dict]:
    """Convert Risk dataclasses to template-ready dicts with compiled JS expressions."""
    q_text = {q.id: q.text for q in questions}
    result = []
    for risk in risks:
        ids = list(
            dict.fromkeys(qid for rule in risk.rules for qid in rule.referenced_question_ids())
        )
        result.append(
            {
                "id": risk.id,
                "name": risk.name,
                "description": risk.description,
                "default_likelihood": risk.default_likelihood,
                "default_consequence": risk.default_consequence,
                "rules_js": [rule.to_js() for rule in risk.rules],
                "questions": [{"id": qid, "text": q_text[qid]} for qid in ids],
            }
        )
    return result


def prepare_controls(
    controls: list[Control],
    risk_dicts: list[dict],
) -> list[dict]:
    """Build control getters and attach per-risk control lists to risk dicts."""
    control_getters = [{"id": ctrl.id, "js": ctrl.presence_js()} for ctrl in controls]

    # Index risk dicts by id for fast lookup
    risk_by_id = {r["id"]: r for r in risk_dicts}

    # Group control effects by risk_id
    for risk_dict in risk_dicts:
        risk_dict["controls"] = []

    for ctrl in controls:
        for effect in ctrl.effects:
            if effect.risk_id in risk_by_id:
                risk_by_id[effect.risk_id]["controls"].append(
                    {
                        "id": ctrl.id,
                        "name": ctrl.name,
                        "reduces_likelihood": effect.reduces_likelihood,
                        "reduces_consequence": effect.reduces_consequence,
                    }
                )

    return control_getters


def validate_question_ids(
    questions: list[Question], risks: list[Risk], controls: list[Control]
) -> None:
    """Raise ValueError if any risk rule or control references a nonexistent question ID."""
    valid_ids = {q.id for q in questions}
    errors: list[str] = []
    for risk in risks:
        for rule in risk.rules:
            for qid in rule.referenced_question_ids():
                if qid not in valid_ids:
                    errors.append(f"Risk '{risk.id}' references unknown question '{qid}'")
    for ctrl in controls:
        if ctrl.question_id not in valid_ids:
            errors.append(f"Control '{ctrl.id}' references unknown question '{ctrl.question_id}'")
    if errors:
        raise ValueError("Invalid question ID references:\n  " + "\n  ".join(errors))


def render_form(
    sections: list[Section], risks: list[Risk], controls: list[Control] | None = None
) -> str:
    """Render the form page HTML from sections and risks."""
    env = create_environment()
    template = env.get_template("page.html.j2")
    questions = all_questions(sections)
    validate_question_ids(questions, risks, controls or [])
    section_dicts = prepare_sections(sections)
    question_dicts = [
        q for sec in section_dicts for sub in sec["subsections"] for q in sub["questions"]
    ]
    risk_dicts = prepare_risks(risks, questions)
    control_getters = prepare_controls(controls or [], risk_dicts)
    return template.render(
        sections=section_dicts,
        questions=question_dicts,
        risks=risk_dicts,
        control_getters=control_getters,
        likelihoods_js=json.dumps(list(config.LIKELIHOODS)),
        consequences_js=json.dumps(list(config.CONSEQUENCES)),
        risk_levels=list(config.RISK_LEVELS),
        risk_level_colours=config.RISK_LEVEL_COLOURS,
        risk_matrix_js=json.dumps(config.RISK_MATRIX),
    )
