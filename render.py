import json
from collections.abc import Sequence
from dataclasses import dataclass

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
    """Create a Jinja2 environment loading from the templates directory.

    Autoescape is enabled for HTML-ish templates only. `app.js.j2` renders
    JavaScript and must NOT be autoescaped — otherwise quote characters in
    compiled getter bodies become HTML entities that break the emitted JS.
    """
    return Environment(
        loader=FileSystemLoader(config.templates_dir),
        autoescape=select_autoescape(
            enabled_extensions=("html", "htm", "xml", "html.j2"),
            default_for_string=False,
            default=False,
        ),
        trim_blocks=True,
        lstrip_blocks=True,
    )


# ---------------------------------------------------------------------------
# Template view dataclasses
# ---------------------------------------------------------------------------
#
# Jinja2 traverses these via attribute access directly. `visibility_js == "true"`
# is the always-visible sentinel — templates should suppress the x-show attribute
# in that case so the rendered HTML stays clean.


@dataclass(frozen=True)
class QuestionView:
    id: str
    text: str
    type: str
    guidance: str | None
    detail_id: str | None
    visibility_js: str


@dataclass(frozen=True)
class SubSectionView:
    title: str
    description: str
    questions: tuple[QuestionView, ...]
    visibility_js: str


@dataclass(frozen=True)
class SectionView:
    id: str
    title: str
    description: str
    subsections: tuple[SubSectionView, ...]


@dataclass(frozen=True)
class PropertyGetter:
    id: str
    js_body: str


@dataclass(frozen=True)
class ControlGetter:
    id: str
    js: str


@dataclass(frozen=True)
class DetailView:
    id: str
    description: str
    show_js: str


@dataclass(frozen=True)
class RiskView:
    id: str
    description: str
    guidance: str | None
    rules_js: tuple[str, ...]
    controls: tuple[Control, ...]
    relevant_details: tuple[DetailView, ...]


# ---------------------------------------------------------------------------
# JS compilation helpers
# ---------------------------------------------------------------------------


def _compile_property_getter(
    prop: Property,
    question_for_prop: dict[str, BinaryQuestion],
) -> str:
    """Compile a JS getter body for a single property.

    The getter handles parent cascade (based on activation mode) then direct
    question state. Returns a JS expression body (without the `get` wrapper).

    A property with parents and no question is treated as a pure computed
    truth: once the parent cascade is satisfied (all-of / any-of), the
    property is true. This lets a property name an AND/OR over its parents
    without forcing a redundant question on the user.
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
    elif prop.parents:
        # No question — parent cascade already satisfied means the property holds.
        lines.append("return true;")
    else:
        # No parents and no question — property is unreachable.
        lines.append("return null;")

    return "\n".join(lines)


def _compile_question_visibility(
    q: Question,
    prop_by_id: dict[str, Property],
) -> str:
    """Compile a JS expression for whether a question should be visible.

    A question is visible when at least one of its target properties has all its
    required parents answered affirmatively (`=== true`). Unanswered parents
    (`null`) keep the question hidden, so the form grows progressively as the
    user answers. Root properties (no parents) are always visible.
    """
    if not q.properties:
        return "true"

    parts: list[str] = []
    for pid in q.properties:
        prop = prop_by_id[pid]
        if not prop.parents:
            # Root property — always visible
            parts.append("true")
        elif prop.activation == "all":
            checks = " && ".join(f"prop_{parent} === true" for parent in prop.parents)
            parts.append(f"({checks})")
        else:  # "any"
            checks = " || ".join(f"prop_{parent} === true" for parent in prop.parents)
            parts.append(f"({checks})")

    # If any target property is always visible, the question is always visible
    if any(p == "true" for p in parts):
        return "true"
    return " || ".join(parts)


def _detail_show_js(props: Sequence[str]) -> str:
    """JS expression: true when any of the detail's properties is active (true)."""
    if not props:
        return "false"
    return " || ".join(f"prop_{pid} === true" for pid in props)


# ---------------------------------------------------------------------------
# View construction
# ---------------------------------------------------------------------------


def _build_question_view(q: Question, visibility_js: str) -> QuestionView:
    return QuestionView(
        id=q.id,
        text=q.text,
        type=q.type,
        guidance=q.guidance,
        detail_id=q.detail_id if isinstance(q, DetailQuestion) else None,
        visibility_js=visibility_js,
    )


def _build_subsection_view(
    sub: SubSection,
    question_visibility: dict[str, str],
) -> SubSectionView:
    q_views = tuple(
        _build_question_view(q, question_visibility.get(q.id, "true")) for q in sub.questions
    )
    # Subsection is always visible if any of its questions is; otherwise the
    # OR of the conditional-question expressions.
    if any(qv.visibility_js == "true" for qv in q_views) or not q_views:
        vis = "true"
    else:
        vis = " || ".join(qv.visibility_js for qv in q_views)
    return SubSectionView(
        title=sub.title,
        description=sub.description,
        questions=q_views,
        visibility_js=vis,
    )


def _build_section_views(
    sections: Sequence[Section],
    question_visibility: dict[str, str],
) -> tuple[SectionView, ...]:
    return tuple(
        SectionView(
            id=section.id,
            title=section.title,
            description=section.description,
            subsections=tuple(
                _build_subsection_view(sub, question_visibility) for sub in section.subsections
            ),
        )
        for section in sections
    )


def _build_risk_views(
    risks: Sequence[Risk],
    controls: Sequence[Control],
    details: Sequence[Detail],
) -> tuple[RiskView, ...]:
    controls_by_risk: dict[str, list[Control]] = {r.id: [] for r in risks}
    for ctrl in controls:
        for effect in ctrl.effects:
            if effect.risk_id in controls_by_risk:
                controls_by_risk[effect.risk_id].append(ctrl)

    result: list[RiskView] = []
    for risk in risks:
        risk_prop_ids = {cond.property for cond in risk.conditions}
        relevant = tuple(
            DetailView(id=d.id, description=d.description, show_js=_detail_show_js(d.properties))
            for d in details
            if risk_prop_ids & set(d.properties)
        )
        result.append(
            RiskView(
                id=risk.id,
                description=risk.description,
                guidance=risk.guidance,
                rules_js=risk.rules_js,
                controls=tuple(controls_by_risk[risk.id]),
                relevant_details=relevant,
            )
        )
    return tuple(result)


# ---------------------------------------------------------------------------
# Top-level render
# ---------------------------------------------------------------------------


def _build_template_context(
    sections: Sequence[Section],
    risks: Sequence[Risk],
    controls: Sequence[Control] | None = None,
    properties: Sequence[Property] | None = None,
    details: Sequence[Detail] | None = None,
) -> dict:
    """Build the shared template context used by both page.html.j2 and app.js.j2."""
    controls = controls or ()
    properties = properties or ()
    details = details or ()
    questions = all_questions(sections)

    # Only BinaryQuestions set property state; DetailQuestions use properties for visibility only.
    question_for_prop: dict[str, BinaryQuestion] = {}
    for q in questions:
        if isinstance(q, BinaryQuestion):
            for pid in q.properties:
                question_for_prop[pid] = q

    prop_by_id = {p.id: p for p in properties}

    property_getters = tuple(
        PropertyGetter(id=prop.id, js_body=_compile_property_getter(prop, question_for_prop))
        for prop in properties
    )
    question_visibility = {q.id: _compile_question_visibility(q, prop_by_id) for q in questions}

    section_views = _build_section_views(sections, question_visibility)
    question_views = tuple(
        q for s in section_views for sub in s.subsections for q in sub.questions
    )
    risk_views = _build_risk_views(risks, controls, details)
    control_getters = tuple(
        ControlGetter(id=ctrl.id, js=f"this.prop_{ctrl.property} === true") for ctrl in controls
    )
    detail_ids = [d.id for d in details]

    return {
        "sections": section_views,
        "questions": question_views,
        "risks": risk_views,
        "control_getters": control_getters,
        "property_getters": property_getters,
        "detail_ids": detail_ids,
        "likelihoods": list(config.LIKELIHOODS),
        "consequences": list(config.CONSEQUENCES),
        "likelihoods_js": json.dumps(list(config.LIKELIHOODS)),
        "consequences_js": json.dumps(list(config.CONSEQUENCES)),
        "risk_levels": list(config.RISK_LEVELS),
        "risk_level_colours": config.RISK_LEVEL_COLOURS,
        "risk_matrix_js": json.dumps(config.RISK_MATRIX),
        "answers_init_js": json.dumps({q.id: "" for q in question_views}),
        "details_init_js": json.dumps({did: "" for did in detail_ids}),
        "control_effectiveness_init_js": json.dumps({r.id: "" for r in risk_views}),
        "residual_likelihood_init_js": json.dumps({r.id: "" for r in risk_views}),
        "residual_consequence_init_js": json.dumps({r.id: "" for r in risk_views}),
        "justifications_init_js": json.dumps({r.id: "" for r in risk_views}),
        "mandated_controls_init_js": json.dumps(
            {r.id: {c.id: False for c in r.controls} for r in risk_views}
        ),
        "mandated_comments_init_js": json.dumps(
            {r.id: {c.id: "" for c in r.controls} for r in risk_views}
        ),
        "question_ids_js": json.dumps([q.id for q in question_views]),
        "detail_ids_js": json.dumps(detail_ids),
        "risk_ids_js": json.dumps([r.id for r in risk_views]),
        "control_ids_js": json.dumps({r.id: [c.id for c in r.controls] for r in risk_views}),
    }


def render_form(
    sections: Sequence[Section],
    risks: Sequence[Risk],
    controls: Sequence[Control] | None = None,
    properties: Sequence[Property] | None = None,
    details: Sequence[Detail] | None = None,
) -> str:
    """Render the form page HTML from sections, risks, properties, and details."""
    env = create_environment()
    template = env.get_template("page.html.j2")
    context = _build_template_context(sections, risks, controls, properties, details)
    return template.render(**context)


def render_app_js(
    sections: Sequence[Section],
    risks: Sequence[Risk],
    controls: Sequence[Control] | None = None,
    properties: Sequence[Property] | None = None,
    details: Sequence[Detail] | None = None,
) -> str:
    """Render the Alpine.js component factory as a standalone JS file."""
    env = create_environment()
    template = env.get_template("app.js.j2")
    context = _build_template_context(sections, risks, controls, properties, details)
    return template.render(**context)
