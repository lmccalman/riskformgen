from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field

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
    type: str = field(default="binary", init=False)


Question = BinaryQuestion


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
    """Maps a set of properties to a {likelihood, consequence} result."""

    properties: tuple[str, ...]
    mode: str  # "any" or "all"
    likelihood: str
    consequence: str

    def to_js(self) -> str:
        props = ", ".join(f"this.prop_{pid}" for pid in self.properties)
        check = "some" if self.mode == "any" else "every"
        result = _js_result(self.likelihood, self.consequence)
        return f"[{props}].{check}(p => p === true) ? {result} : null"


@dataclass(frozen=True)
class Risk:
    """A risk whose level is derived from property-based conditions."""

    id: str
    description: str
    conditions: tuple[ConditionMapping, ...]


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ControlEffect:
    """Links a control to a risk, indicating which dimensions it reduces."""

    risk_id: str
    reduces_likelihood: bool = False
    reduces_consequence: bool = False

    def __post_init__(self) -> None:
        if not self.reduces_likelihood and not self.reduces_consequence:
            raise ValueError(
                "ControlEffect requires at least one of reduces_likelihood or reduces_consequence"
            )


@dataclass(frozen=True)
class Control:
    """A safeguard whose presence is determined by a property."""

    id: str
    description: str
    property: str
    effects: tuple[ControlEffect, ...]


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Property:
    """A boolean property node in a DAG. Parents must hold when this property does."""

    id: str
    description: str
    parents: tuple[str, ...] = ()
    activation: str = "all"  # "all" or "any"
