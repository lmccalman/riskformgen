"""Validation wrapper that converts Pydantic schemas to frozen dataclasses
and runs all parse.py validators, collecting errors."""

from __future__ import annotations

from models import (
    BinaryQuestion,
    ConditionMapping,
    Control,
    ControlEffect,
    Detail,
    DetailQuestion,
    Property,
    Risk,
)
from parse import (
    validate_control_properties,
    validate_control_risk_ids,
    validate_detail_properties,
    validate_detail_questions,
    validate_property_dag,
    validate_question_properties,
    validate_risk_properties,
)

from .schemas import SectionSchema, SpecPayload, ValidationErrorItem


def _to_properties(spec: SpecPayload) -> list[Property]:
    return [
        Property(
            id=p.id,
            description=p.description,
            parents=tuple(p.parents),
            activation=p.activation,
        )
        for p in spec.properties
    ]


def _to_details(spec: SpecPayload) -> list[Detail]:
    return [
        Detail(id=d.id, description=d.description, properties=tuple(d.properties))
        for d in spec.details
    ]


def _to_risks(spec: SpecPayload) -> list[Risk]:
    return [
        Risk(
            id=r.id,
            description=r.description,
            conditions=tuple(
                ConditionMapping(
                    properties=tuple(c.properties),
                    mode=c.mode,
                    likelihood=c.likelihood,
                    consequence=c.consequence,
                )
                for c in r.conditions
            ),
        )
        for r in spec.risks
    ]


def _to_controls(spec: SpecPayload) -> list[Control]:
    return [
        Control(
            id=c.id,
            description=c.description,
            property=c.property,
            effects=tuple(ControlEffect(risk_id=e.risk_id) for e in c.effects),
        )
        for c in spec.controls
    ]


def _to_questions(sections: list[SectionSchema], details: list[Detail]):
    """Build frozen question dataclasses from section schemas."""
    details_by_id = {d.id: d for d in details}
    questions = []
    for section in sections:
        for subsection in section.subsections:
            for q in subsection.questions:
                if q.type == "binary":
                    questions.append(
                        BinaryQuestion(
                            id=q.id,
                            text=q.text,
                            properties=tuple(q.properties),
                            guidance=q.guidance,
                        )
                    )
                elif q.type == "detail":
                    detail = details_by_id.get(q.detail_id or "")
                    props = detail.properties if detail else ()
                    questions.append(
                        DetailQuestion(
                            id=q.id,
                            text=q.text,
                            detail_id=q.detail_id or "",
                            properties=props,
                            guidance=q.guidance,
                        )
                    )
    return questions


def validate_spec(spec: SpecPayload) -> list[ValidationErrorItem]:
    """Run all validators, collecting errors instead of raising on the first."""
    errors: list[ValidationErrorItem] = []

    # Convert to frozen dataclasses
    try:
        properties = _to_properties(spec)
    except (ValueError, TypeError) as e:
        errors.append(ValidationErrorItem(file="properties", message=str(e)))
        return errors  # can't validate further without properties

    try:
        details = _to_details(spec)
    except (ValueError, TypeError) as e:
        errors.append(ValidationErrorItem(file="details", message=str(e)))
        details = []

    try:
        risks = _to_risks(spec)
    except (ValueError, TypeError) as e:
        errors.append(ValidationErrorItem(file="risks", message=str(e)))
        risks = []

    try:
        controls = _to_controls(spec)
    except (ValueError, TypeError) as e:
        errors.append(ValidationErrorItem(file="controls", message=str(e)))
        controls = []

    try:
        questions = _to_questions(spec.sections, details)
    except (ValueError, TypeError) as e:
        errors.append(ValidationErrorItem(file="sections", message=str(e)))
        questions = []

    # Run each validator
    validators: list[tuple[object, list[object], str]] = [
        (validate_property_dag, [properties], "properties"),
        (validate_question_properties, [questions, properties], "sections"),
        (validate_risk_properties, [risks, properties], "risks"),
        (validate_control_properties, [controls, properties], "controls"),
        (validate_control_risk_ids, [controls, risks], "controls"),
        (validate_detail_properties, [details, properties], "details"),
        (validate_detail_questions, [questions, details], "sections"),
    ]

    for validator, args, file_label in validators:
        try:
            validator(*args)  # type: ignore[operator]
        except ValueError as e:
            errors.append(ValidationErrorItem(file=file_label, message=str(e)))

    return errors
