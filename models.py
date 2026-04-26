from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BinaryQuestion:
    """A yes/no question that enables/disables a set of properties."""

    id: str
    text: str
    properties: tuple[str, ...]
    guidance: str | None = None
    type: Literal["binary"] = field(default="binary", init=False)


@dataclass(frozen=True)
class DetailQuestion:
    """A free-text question that stores user input against a Detail.

    Properties are copied from the referenced Detail at parse time so the
    existing visibility compilation system works without modification.
    """

    id: str
    text: str
    detail_id: str
    properties: tuple[str, ...]  # copied from Detail.properties at parse time
    guidance: str | None = None
    type: Literal["detail"] = field(default="detail", init=False)


Question = BinaryQuestion | DetailQuestion


# ---------------------------------------------------------------------------
# Form structure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubSection:
    """A visual grouping of questions within a section."""

    title: str
    description: str
    questions: tuple[Question, ...]


@dataclass(frozen=True)
class Section:
    """A major form section rendered as its own tab."""

    id: str
    title: str
    description: str
    subsections: tuple[SubSection, ...]


def all_questions(sections: Sequence[Section]) -> list[Question]:
    """Flatten sections into a single question list."""
    return [q for s in sections for sub in s.subsections for q in sub.questions]


# ---------------------------------------------------------------------------
# Risk model
# ---------------------------------------------------------------------------


def _js_result(likelihood: str, consequence: str) -> str:
    """Build a JS object literal string for a {likelihood, consequence} result."""
    return f"{{likelihood: {json.dumps(likelihood)}, consequence: {json.dumps(consequence)}}}"


@dataclass(frozen=True)
class ConditionMapping:
    """Maps a single property to a {likelihood, consequence} result."""

    property: str
    likelihood: str
    consequence: str

    def to_js(self) -> str:
        result = _js_result(self.likelihood, self.consequence)
        return f"this.prop_{self.property} === true ? {result} : null"


@dataclass(frozen=True)
class Risk:
    """A risk whose level is derived from property-based conditions."""

    id: str
    description: str
    conditions: tuple[ConditionMapping, ...]
    guidance: str | None = None

    @property
    def rules_js(self) -> tuple[str, ...]:
        return tuple(c.to_js() for c in self.conditions)


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ControlEffect:
    """Links a control to a risk it addresses."""

    risk_id: str


@dataclass(frozen=True)
class Control:
    """A safeguard whose presence is determined by a property."""

    id: str
    description: str
    property: str
    effects: tuple[ControlEffect, ...]


# ---------------------------------------------------------------------------
# Details
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Detail:
    """A contextual topic whose free-text value is displayed in risk cards
    when its associated properties are active."""

    id: str
    description: str
    properties: tuple[str, ...]


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Property:
    """A boolean property node in a DAG. Parents must hold when this property does."""

    id: str
    description: str
    parents: tuple[str, ...] = ()
    activation: Literal["all", "any"] = "all"
