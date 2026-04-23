"""Pydantic models mirroring the frozen dataclasses in models.py."""

from __future__ import annotations

from pydantic import BaseModel


class PropertySchema(BaseModel):
    id: str
    description: str
    parents: list[str] = []
    activation: str = "all"


class ConditionMappingSchema(BaseModel):
    properties: list[str]
    mode: str = "all"
    likelihood: str
    consequence: str


class RiskSchema(BaseModel):
    id: str
    description: str
    conditions: list[ConditionMappingSchema]


class ControlEffectSchema(BaseModel):
    risk_id: str


class ControlSchema(BaseModel):
    id: str
    description: str
    property: str
    effects: list[ControlEffectSchema]


class DetailSchema(BaseModel):
    id: str
    description: str
    properties: list[str]


class QuestionSchema(BaseModel):
    type: str  # "binary" or "detail"
    id: str
    text: str
    properties: list[str] = []
    guidance: str | None = None
    detail_id: str | None = None  # only for type="detail"


class SubSectionSchema(BaseModel):
    title: str
    description: str
    questions: list[QuestionSchema]


class SectionSchema(BaseModel):
    id: str
    title: str
    description: str
    subsections: list[SubSectionSchema]


class ConstantsSchema(BaseModel):
    likelihoods: list[str]
    consequences: list[str]


class SpecPayload(BaseModel):
    properties: list[PropertySchema]
    sections: list[SectionSchema]
    risks: list[RiskSchema]
    controls: list[ControlSchema]
    details: list[DetailSchema]


class SpecResponse(SpecPayload):
    constants: ConstantsSchema


class ValidationErrorItem(BaseModel):
    file: str
    message: str


class ValidationResult(BaseModel):
    valid: bool
    errors: list[ValidationErrorItem]


class SaveResult(BaseModel):
    ok: bool
    errors: list[ValidationErrorItem]


class RebuildResult(BaseModel):
    ok: bool
    message: str
