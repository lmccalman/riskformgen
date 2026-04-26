import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

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
from registry import SystemRecord, aggregate_residual_level


def create_environment() -> Environment:
    """Create a Jinja2 environment loading from the templates directory.

    Autoescape is enabled for HTML-ish templates only. The `app-*.js.j2`
    templates render JavaScript and must NOT be autoescaped — otherwise quote
    characters in compiled getter bodies become HTML entities that break the
    emitted JS.
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
    """Build the shared template context used by every page and factory template."""
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
        "risk_levels_js": json.dumps(list(config.RISK_LEVELS)),
        "risk_level_colours": config.RISK_LEVEL_COLOURS,
        "risk_matrix_js": json.dumps(config.RISK_MATRIX),
        "answers_init_js": json.dumps({q.id: "" for q in question_views}),
        "details_init_js": json.dumps({did: "" for did in detail_ids}),
        "control_effectiveness_init_js": json.dumps({r.id: "" for r in risk_views}),
        "residual_likelihood_init_js": json.dumps({r.id: "" for r in risk_views}),
        "residual_consequence_init_js": json.dumps({r.id: "" for r in risk_views}),
        "justifications_init_js": json.dumps({r.id: "" for r in risk_views}),
        "aggregate_residual_level_init_js": json.dumps(""),
        "aggregate_residual_justification_init_js": json.dumps(""),
        "mandated_controls_init_js": json.dumps(
            {r.id: {c.id: False for c in r.controls} for r in risk_views}
        ),
        "mandated_comments_init_js": json.dumps(
            {r.id: {c.id: "" for c in r.controls} for r in risk_views}
        ),
        "question_ids_js": json.dumps([q.id for q in question_views]),
        "detail_ids_js": json.dumps(detail_ids),
        "property_ids_js": json.dumps([p.id for p in property_getters]),
        "risk_ids_js": json.dumps([r.id for r in risk_views]),
        "control_ids_js": json.dumps({r.id: [c.id for c in r.controls] for r in risk_views}),
        "risk_conditions_js": json.dumps(
            {r.id: list(dict.fromkeys(c.property for c in r.conditions)) for r in risks}
        ),
    }


def render_landing() -> str:
    """Render the landing page HTML (no Alpine, no form data)."""
    env = create_environment()
    template = env.get_template("landing.html.j2")
    return template.render()


def render_questionnaire(
    sections: Sequence[Section],
    properties: Sequence[Property] | None = None,
    details: Sequence[Detail] | None = None,
) -> str:
    """Render the questionnaire page HTML (system owner view)."""
    env = create_environment()
    template = env.get_template("questionnaire.html.j2")
    context = _build_template_context(sections, [], None, properties, details)
    return template.render(**context)


def render_assessment(
    sections: Sequence[Section],
    risks: Sequence[Risk],
    controls: Sequence[Control] | None = None,
    properties: Sequence[Property] | None = None,
    details: Sequence[Detail] | None = None,
) -> str:
    """Render the assessment page HTML (assessor view)."""
    env = create_environment()
    template = env.get_template("assessment.html.j2")
    context = _build_template_context(sections, risks, controls, properties, details)
    return template.render(**context)


def render_registry_index(records: Sequence[SystemRecord]) -> str:
    """Render the registry index page — table of all committed systems."""
    env = create_environment()
    template = env.get_template("registry.html.j2")
    rows = [_build_registry_row(r) for r in records]
    return template.render(
        rows=rows,
        risk_level_colours=config.RISK_LEVEL_COLOURS,
        asset_prefix="",
    )


def render_registry_system(
    record: SystemRecord,
    sections: Sequence[Section],
    risks: Sequence[Risk],
    controls: Sequence[Control],
    properties: Sequence[Property],
    details: Sequence[Detail],
) -> str:
    """Render the per-system detail page for one registry record."""
    env = create_environment()
    template = env.get_template("registry_system.html.j2")
    view = _build_registry_system_view(record, sections, risks, controls, properties, details)
    return template.render(
        **view,
        risk_level_colours=config.RISK_LEVEL_COLOURS,
        asset_prefix="../",
    )


# ---------------------------------------------------------------------------
# Registry view construction
# ---------------------------------------------------------------------------


def _format_date(iso: str) -> str:
    """Trim an ISO timestamp to YYYY-MM-DD for display, or return '—' if empty."""
    if not iso:
        return "—"
    return iso[:10]


def _build_registry_row(record: SystemRecord) -> dict[str, Any]:
    level = (
        "not_applicable"
        if record.assessment is None
        else aggregate_residual_level(record, config.RISK_LEVELS)
    )
    return {
        "slug": record.slug,
        "name": record.meta.name,
        "owner": record.meta.owner,
        "last_assessed": _format_date(record.exported_at),
        "has_assessment": record.assessment is not None,
        "residual_level": level,
    }


def _question_visible(
    q: Question,
    prop_by_id: dict[str, Property],
    properties_state: dict[str, Any],
) -> bool:
    """Mirror of `_compile_question_visibility` evaluated server-side.

    A question is visible when at least one of its target properties is
    reachable — i.e. the property's parents satisfy its activation mode.
    Root properties (no parents) are always visible. Uses the loaded
    `properties_state` dict (resolved at export time) rather than
    re-evaluating the cascade.
    """
    if not q.properties:
        return True
    for pid in q.properties:
        prop = prop_by_id.get(pid)
        if prop is None or not prop.parents:
            return True
        if prop.activation == "all":
            if all(properties_state.get(pp) is True for pp in prop.parents):
                return True
        else:
            if any(properties_state.get(pp) is True for pp in prop.parents):
                return True
    return False


@dataclass(frozen=True)
class RegistryQuestionView:
    id: str
    text: str
    type: str
    detail_id: str | None
    answer: str
    detail_text: str
    visible: bool


@dataclass(frozen=True)
class RegistrySubSectionView:
    title: str
    description: str
    questions: tuple[RegistryQuestionView, ...]
    visible: bool


@dataclass(frozen=True)
class RegistrySectionView:
    title: str
    description: str
    subsections: tuple[RegistrySubSectionView, ...]
    visible: bool


def _build_registry_section_views(
    sections: Sequence[Section],
    properties: Sequence[Property],
    properties_state: dict[str, Any],
    answers: dict[str, str],
    details: dict[str, str],
) -> tuple[RegistrySectionView, ...]:
    prop_by_id = {p.id: p for p in properties}
    out_sections: list[RegistrySectionView] = []
    for section in sections:
        out_subs: list[RegistrySubSectionView] = []
        for sub in section.subsections:
            qs: list[RegistryQuestionView] = []
            for q in sub.questions:
                visible = _question_visible(q, prop_by_id, properties_state)
                detail_id = q.detail_id if isinstance(q, DetailQuestion) else None
                qs.append(
                    RegistryQuestionView(
                        id=q.id,
                        text=q.text,
                        type=q.type,
                        detail_id=detail_id,
                        answer=str(answers.get(q.id, "") or ""),
                        detail_text=str(details.get(detail_id, "") or "") if detail_id else "",
                        visible=visible,
                    )
                )
            out_subs.append(
                RegistrySubSectionView(
                    title=sub.title,
                    description=sub.description,
                    questions=tuple(qs),
                    visible=any(qv.visible for qv in qs),
                )
            )
        out_sections.append(
            RegistrySectionView(
                title=section.title,
                description=section.description,
                subsections=tuple(out_subs),
                visible=any(sv.visible for sv in out_subs),
            )
        )
    return tuple(out_sections)


@dataclass(frozen=True)
class RegistryControlView:
    id: str
    description: str
    present: bool


@dataclass(frozen=True)
class RegistryMandatedControlView:
    id: str
    description: str
    mandated: bool
    comment: str


@dataclass(frozen=True)
class RegistryDetailView:
    description: str
    text: str


@dataclass(frozen=True)
class RegistryRiskView:
    id: str
    description: str
    guidance: str | None
    inherent_likelihood: str
    inherent_consequence: str
    inherent_level: str
    residual_likelihood: str
    residual_consequence: str
    residual_level: str
    effectiveness: str
    justification: str
    controls: tuple[RegistryControlView, ...]
    mandated_controls: tuple[RegistryMandatedControlView, ...]
    relevant_details: tuple[RegistryDetailView, ...]


def _build_registry_risk_views(
    risks: Sequence[Risk],
    controls: Sequence[Control],
    details: Sequence[Detail],
    record: SystemRecord,
) -> tuple[RegistryRiskView, ...]:
    if record.assessment is None:
        return ()

    assessment = record.assessment
    inherent_block = assessment.get("inherent") or {}
    properties_state = record.questionnaire.get("properties") or {}
    detail_values = record.questionnaire.get("details") or {}

    controls_by_risk: dict[str, list[Control]] = {r.id: [] for r in risks}
    for ctrl in controls:
        for effect in ctrl.effects:
            if effect.risk_id in controls_by_risk:
                controls_by_risk[effect.risk_id].append(ctrl)

    out: list[RegistryRiskView] = []
    for risk in risks:
        inh = inherent_block.get(risk.id) or {}
        inh_level = inh.get("level", "not_applicable")
        if inh_level == "not_applicable":
            continue

        eff = (assessment.get("control_effectiveness") or {}).get(risk.id) or "ineffective"
        res_l = (assessment.get("residual_likelihood") or {}).get(risk.id) or ""
        res_c = (assessment.get("residual_consequence") or {}).get(risk.id) or ""
        residual_level = _registry_residual_level(inh_level, eff, res_l, res_c)
        residual_likelihood = inh.get("likelihood") or "" if eff != "partial" else res_l
        residual_consequence = inh.get("consequence") or "" if eff != "partial" else res_c

        ctrl_views = tuple(
            RegistryControlView(
                id=c.id,
                description=c.description,
                present=bool(properties_state.get(c.property) is True),
            )
            for c in controls_by_risk[risk.id]
        )

        mandated_block = (assessment.get("mandated_controls") or {}).get(risk.id) or {}
        comment_block = (assessment.get("mandated_comments") or {}).get(risk.id) or {}
        mandated_views = tuple(
            RegistryMandatedControlView(
                id=c.id,
                description=c.description,
                mandated=bool(mandated_block.get(c.id, False)),
                comment=str(comment_block.get(c.id, "") or ""),
            )
            for c in controls_by_risk[risk.id]
            if not bool(properties_state.get(c.property) is True)
        )

        risk_prop_ids = {cond.property for cond in risk.conditions}
        relevant_details = tuple(
            RegistryDetailView(
                description=d.description,
                text=str(detail_values.get(d.id, "") or ""),
            )
            for d in details
            if (risk_prop_ids & set(d.properties))
            and any(properties_state.get(pid) is True for pid in d.properties)
            and detail_values.get(d.id)
        )

        out.append(
            RegistryRiskView(
                id=risk.id,
                description=risk.description,
                guidance=risk.guidance,
                inherent_likelihood=inh.get("likelihood") or "",
                inherent_consequence=inh.get("consequence") or "",
                inherent_level=inh_level,
                residual_likelihood=residual_likelihood,
                residual_consequence=residual_consequence,
                residual_level=residual_level,
                effectiveness=eff,
                justification=str((assessment.get("justifications") or {}).get(risk.id, "") or ""),
                controls=ctrl_views,
                mandated_controls=mandated_views,
                relevant_details=relevant_details,
            )
        )
    return tuple(out)


def _registry_residual_level(
    inherent_level: str, effectiveness: str, res_l: str, res_c: str
) -> str:
    if effectiveness == "ineffective":
        return inherent_level
    if effectiveness == "controlled":
        return "controlled"
    if not res_l or not res_c:
        return inherent_level
    return config.RISK_MATRIX.get(res_l, {}).get(res_c, "not_applicable")


def _build_registry_system_view(
    record: SystemRecord,
    sections: Sequence[Section],
    risks: Sequence[Risk],
    controls: Sequence[Control],
    properties: Sequence[Property],
    details: Sequence[Detail],
) -> dict[str, Any]:
    answers = record.questionnaire.get("answers") or {}
    detail_values = record.questionnaire.get("details") or {}
    properties_state = record.questionnaire.get("properties") or {}

    section_views = _build_registry_section_views(
        sections, properties, properties_state, answers, detail_values
    )
    risk_views = _build_registry_risk_views(risks, controls, details, record)

    if record.assessment is None:
        aggregate_level = "not_applicable"
        aggregate_justification = ""
    else:
        aggregate_level = aggregate_residual_level(record, config.RISK_LEVELS)
        aggregate_justification = str(
            record.assessment.get("aggregate_residual_justification", "") or ""
        )

    return {
        "record": record,
        "meta": record.meta,
        "slug": record.slug,
        "exported_at": _format_date(record.exported_at),
        "sections": section_views,
        "risks": risk_views,
        "has_assessment": record.assessment is not None,
        "aggregate_residual_level": aggregate_level,
        "aggregate_residual_justification": aggregate_justification,
    }


def render_questionnaire_app_js(
    sections: Sequence[Section],
    properties: Sequence[Property] | None = None,
    details: Sequence[Detail] | None = None,
) -> str:
    """Render the Alpine factory for the questionnaire view as a standalone JS file."""
    env = create_environment()
    template = env.get_template("app-questionnaire.js.j2")
    context = _build_template_context(sections, [], None, properties, details)
    return template.render(**context)


def render_assessment_app_js(
    sections: Sequence[Section],
    risks: Sequence[Risk],
    controls: Sequence[Control] | None = None,
    properties: Sequence[Property] | None = None,
    details: Sequence[Detail] | None = None,
) -> str:
    """Render the Alpine factory for the assessment view as a standalone JS file."""
    env = create_environment()
    template = env.get_template("app-assessment.js.j2")
    context = _build_template_context(sections, risks, controls, properties, details)
    return template.render(**context)
