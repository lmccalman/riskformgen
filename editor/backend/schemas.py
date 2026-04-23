"""Pydantic models mirroring the frozen dataclasses in models.py."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _StrictModel(BaseModel):
    """Reject unknown keys so YAML typos surface at load time."""

    model_config = ConfigDict(extra="forbid")


class PropertySchema(_StrictModel):
    id: str
    description: str
    parents: list[str] = []
    activation: str = "all"


class ConditionMappingSchema(_StrictModel):
    properties: list[str]
    mode: str = "all"
    likelihood: str
    consequence: str


class RiskSchema(_StrictModel):
    id: str
    description: str
    conditions: list[ConditionMappingSchema]


class ControlEffectSchema(_StrictModel):
    risk_id: str


class ControlSchema(_StrictModel):
    id: str
    description: str
    property: str
    effects: list[ControlEffectSchema]


class DetailSchema(_StrictModel):
    id: str
    description: str
    properties: list[str]


class QuestionSchema(_StrictModel):
    type: str  # "binary" or "detail"
    id: str
    text: str
    properties: list[str] = []
    guidance: str | None = None
    detail_id: str | None = None  # only for type="detail"


class SubSectionSchema(_StrictModel):
    title: str
    description: str
    questions: list[QuestionSchema]


class SectionSchema(_StrictModel):
    id: str
    title: str
    description: str
    subsections: list[SubSectionSchema]


class ConstantsSchema(_StrictModel):
    likelihoods: list[str]
    consequences: list[str]


class SpecPayload(_StrictModel):
    properties: list[PropertySchema]
    sections: list[SectionSchema]
    risks: list[RiskSchema]
    controls: list[ControlSchema]
    details: list[DetailSchema]


class SpecResponse(SpecPayload):
    constants: ConstantsSchema


class ValidationErrorItem(_StrictModel):
    file: str
    message: str


class ValidationResult(_StrictModel):
    valid: bool
    errors: list[ValidationErrorItem]


class SaveResult(_StrictModel):
    ok: bool
    errors: list[ValidationErrorItem]


class RebuildResult(_StrictModel):
    ok: bool
    message: str
