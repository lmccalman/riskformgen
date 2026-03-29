import json
from collections.abc import Sequence

from jinja2 import Environment, FileSystemLoader, select_autoescape

import config
from models import (
    BinaryQuestion,
    Control,
    Detail,
    DetailQuestion,
    Property,
    Question,
    Risk,
    Section,
    SubSection,
    all_questions,
)


def create_environment() -> Environment:
    """Create a Jinja2 environment loading from the templates directory."""
    return Environment(
        loader=FileSystemLoader(config.templates_dir),
        autoescape=select_autoescape(default=True),
        trim_blocks=True,
        lstrip_blocks=True,
    )


# ---------------------------------------------------------------------------
# Property compilation
# ---------------------------------------------------------------------------


def _compile_property_getter(
    prop: Property,
    question_for_prop: dict[str, BinaryQuestion],
) -> str:
    """Compile a JS getter body for a single property.

    The getter handles parent cascade (based on activation mode) then direct
    question state. Returns a JS expression body (without the `get` wrapper).
    """
    lines: list[str] = []

    # Parent cascade
    if prop.parents:
        if prop.activation == "all":
            for parent_id in prop.parents:
                lines.append(f"if (this.prop_{parent_id} === false) return false;")
            for parent_id in prop.parents:
                lines.append(f"if (this.prop_{parent_id} === null) return null;")
        else:  # "any"
            parent_refs = ", ".join(f"this.prop_{pid}" for pid in prop.parents)
            lines.append(f"const parents = [{parent_refs}];")
            lines.append("if (parents.every(p => p === false)) return false;")
            lines.append("if (!parents.some(p => p === true)) return null;")

    # Direct state from question (if any question sets this property)
    q = question_for_prop.get(prop.id)
    if q:
        qid = json.dumps(q.id)
        lines.append(
            f"return this.answers[{qid}] === 'yes' ? true"
            f" : this.answers[{qid}] === 'no' ? false : null;"
        )
    else:
        lines.append("return null;")

    return "\n".join(lines)


def _compile_question_visibility(
    q: Question,
    prop_by_id: dict[str, Property],
) -> str:
    """Compile a JS expression for whether a question should be visible.

    A question is visible when at least one of its target properties is reachable —
    meaning the property's parents haven't ruled it out (none false for "all" mode,
    not all false for "any" mode). Root properties (no parents) are always reachable.
    """
    if not q.properties:
        return "true"

    parts: list[str] = []
    for pid in q.properties:
        prop = prop_by_id[pid]
        if not prop.parents:
            # Root property — always reachable
            parts.append("true")
        elif prop.activation == "all":
            checks = " && ".join(f"prop_{parent} !== false" for parent in prop.parents)
            parts.append(f"({checks})")
        else:  # "any"
            checks = " || ".join(f"prop_{parent} !== false" for parent in prop.parents)
            parts.append(f"({checks})")

    # If any target property is always reachable, the question is always visible
    if any(p == "true" for p in parts):
        return "true"
    return " || ".join(parts)


def _detail_show_js(props: list[str]) -> str:
    """JS expression: true when any of the detail's properties is active (true)."""
    if not props:
        return "false"
    return " || ".join(f"prop_{pid} === true" for pid in props)


def prepare_properties(
    properties: list[Property],
    questions: Sequence[Question],
) -> tuple[list[dict[str, str]], dict[str, str]]:
    """Compile property getters and question visibility expressions.

    Returns:
        property_getters: list of {id, js_body} for the template
        question_visibility: dict of {question_id: visibility_js_expression}
    """
    # Only BinaryQuestions set property state; DetailQuestions use properties for visibility only
    question_for_prop: dict[str, BinaryQuestion] = {}
    for q in questions:
        if isinstance(q, BinaryQuestion):
            for pid in q.properties:
                question_for_prop[pid] = q

    prop_by_id = {p.id: p for p in properties}

    property_getters = [
        {"id": prop.id, "js_body": _compile_property_getter(prop, question_for_prop)}
        for prop in properties
    ]

    question_visibility = {q.id: _compile_question_visibility(q, prop_by_id) for q in questions}

    return property_getters, question_visibility


# ---------------------------------------------------------------------------
# Section / question preparation
# ---------------------------------------------------------------------------


def _prepare_question(q: Question, visibility_js: str) -> dict:
    """Convert a Question dataclass to a template-ready dict with visibility JS."""
    d: dict = {
        "id": q.id,
        "text": q.text,
        "type": q.type,
        "properties": list(q.properties),
        "guidance": q.guidance,
    }
    if isinstance(q, DetailQuestion):
        d["detail_id"] = q.detail_id
    if visibility_js != "true":
        d["visibility_js"] = visibility_js
    return d


def _prepare_subsection(
    sub: SubSection,
    question_visibility: dict[str, str],
) -> dict:
    """Convert a SubSection to a template-ready dict with compiled visibility JS."""
    q_dicts = [_prepare_question(q, question_visibility.get(q.id, "true")) for q in sub.questions]

    d: dict = {
        "title": sub.title,
        "description": sub.description,
        "questions": q_dicts,
    }

    # Subsection is visible when any of its questions is visible
    vis_exprs = [qd["visibility_js"] for qd in q_dicts if "visibility_js" in qd]
    if vis_exprs:
        # If some questions are always visible, the subsection is always visible
        always_visible = any("visibility_js" not in qd for qd in q_dicts)
        if not always_visible:
            d["visibility_js"] = " || ".join(vis_exprs)

    return d


def prepare_sections(
    sections: list[Section],
    question_visibility: dict[str, str],
) -> list[dict]:
    """Convert Section dataclasses to template-ready nested dicts."""
    return [
        {
            "id": section.id,
            "title": section.title,
            "description": section.description,
            "subsections": [
                _prepare_subsection(sub, question_visibility) for sub in section.subsections
            ],
        }
        for section in sections
    ]


# ---------------------------------------------------------------------------
# Risks and controls
# ---------------------------------------------------------------------------


def prepare_risks(risks: list[Risk], details: list[Detail] | None = None) -> list[dict]:
    """Convert Risk dataclasses to template-ready dicts with compiled JS expressions."""
    _details = details or []

    result = []
    for risk in risks:
        # Collect all property IDs referenced by this risk's conditions
        risk_prop_ids = {pid for cond in risk.conditions for pid in cond.properties}

        relevant_details = [
            {
                "id": d.id,
                "description": d.description,
                "show_js": _detail_show_js(list(d.properties)),
            }
            for d in _details
            if risk_prop_ids & set(d.properties)
        ]

        result.append(
            {
                "id": risk.id,
                "description": risk.description,
                "rules_js": [cond.to_js() for cond in risk.conditions],
                "relevant_details": relevant_details,
            }
        )

    return result


def prepare_controls(
    controls: list[Control],
    risk_dicts: list[dict],
) -> list[dict]:
    """Build control getters and attach per-risk control lists to risk dicts."""
    control_getters = [
        {"id": ctrl.id, "js": f"this.prop_{ctrl.property} === true"} for ctrl in controls
    ]

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
                        "description": ctrl.description,
                        "reduces_likelihood": effect.reduces_likelihood,
                        "reduces_consequence": effect.reduces_consequence,
                    }
                )

    return control_getters


# ---------------------------------------------------------------------------
# Top-level render
# ---------------------------------------------------------------------------


def render_form(
    sections: list[Section],
    risks: list[Risk],
    controls: list[Control] | None = None,
    properties: list[Property] | None = None,
    details: list[Detail] | None = None,
) -> str:
    """Render the form page HTML from sections, risks, properties, and details."""
    env = create_environment()
    template = env.get_template("page.html.j2")
    questions = all_questions(sections)
    property_getters, question_visibility = prepare_properties(properties or [], questions)
    section_dicts = prepare_sections(sections, question_visibility)
    question_dicts = [
        q for sec in section_dicts for sub in sec["subsections"] for q in sub["questions"]
    ]
    risk_dicts = prepare_risks(risks, details)
    control_getters = prepare_controls(controls or [], risk_dicts)
    detail_ids = [d.id for d in (details or [])]
    return template.render(
        sections=section_dicts,
        questions=question_dicts,
        risks=risk_dicts,
        control_getters=control_getters,
        property_getters=property_getters,
        detail_ids=detail_ids,
        likelihoods_js=json.dumps(list(config.LIKELIHOODS)),
        consequences_js=json.dumps(list(config.CONSEQUENCES)),
        risk_levels=list(config.RISK_LEVELS),
        risk_level_colours=config.RISK_LEVEL_COLOURS,
        risk_matrix_js=json.dumps(config.RISK_MATRIX),
    )
