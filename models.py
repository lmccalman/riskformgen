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


def _js_ids(ids: tuple[str, ...]) -> str:
    """Format a tuple of IDs as a JS array literal."""
    return json.dumps(list(ids))


def _js_result(likelihood: str | None, consequence: str | None) -> str:
    """Build a JS object literal string for a {likelihood, consequence} result."""
    lk = json.dumps(likelihood) if likelihood is not None else "null"
    cq = json.dumps(consequence) if consequence is not None else "null"
    return f"{{likelihood: {lk}, consequence: {cq}}}"


@dataclass(frozen=True)
class AnyYesRule:
    """Returns {likelihood, consequence} if any of the given yes/no questions are 'yes'."""

    question_ids: tuple[str, ...]
    likelihood: str | None = None
    consequence: str | None = None

    def __post_init__(self) -> None:
        if self.likelihood is None and self.consequence is None:
            raise ValueError("AnyYesRule requires at least one of likelihood or consequence")

    def to_js(self) -> str:
        ids = _js_ids(self.question_ids)
        result = _js_result(self.likelihood, self.consequence)
        return f"{ids}.some(id => this.answers[id] === 'yes') ? {result} : null"

    def referenced_question_ids(self) -> tuple[str, ...]:
        return self.question_ids


@dataclass(frozen=True)
class CountYesRule:
    """Returns {likelihood, consequence} if at least *threshold* yes/no questions are 'yes'."""

    question_ids: tuple[str, ...]
    threshold: int
    likelihood: str | None = None
    consequence: str | None = None

    def __post_init__(self) -> None:
        if self.likelihood is None and self.consequence is None:
            raise ValueError("CountYesRule requires at least one of likelihood or consequence")

    def to_js(self) -> str:
        ids = _js_ids(self.question_ids)
        result = _js_result(self.likelihood, self.consequence)
        return (
            f"{ids}.filter(id => this.answers[id] === 'yes').length >= {self.threshold}"
            f" ? {result} : null"
        )

    def referenced_question_ids(self) -> tuple[str, ...]:
        return self.question_ids


@dataclass(frozen=True)
class ChoiceMapRule:
    """Maps a multiple-choice answer to {likelihood, consequence} via a lookup dict."""

    question_id: str
    mapping: dict[str, dict[str, str]]

    def to_js(self) -> str:
        # Normalise each entry so both keys are always present (missing → null)
        normalised = {
            answer: {
                "likelihood": dims.get("likelihood"),
                "consequence": dims.get("consequence"),
            }
            for answer, dims in self.mapping.items()
        }
        return f"{json.dumps(normalised)}[this.answers[{json.dumps(self.question_id)}]] || null"

    def referenced_question_ids(self) -> tuple[str, ...]:
        return (self.question_id,)


@dataclass(frozen=True)
class ContainsAnyRule:
    """Returns {likelihood, consequence} if a multi-select answer contains any of *values*."""

    question_id: str
    values: tuple[str, ...]
    likelihood: str | None = None
    consequence: str | None = None

    def __post_init__(self) -> None:
        if self.likelihood is None and self.consequence is None:
            raise ValueError("ContainsAnyRule requires at least one of likelihood or consequence")

    def to_js(self) -> str:
        vals = json.dumps(list(self.values))
        qid = json.dumps(self.question_id)
        result = _js_result(self.likelihood, self.consequence)
        return f"{vals}.some(v => (this.answers[{qid}] || []).includes(v)) ? {result} : null"

    def referenced_question_ids(self) -> tuple[str, ...]:
        return (self.question_id,)


RiskRule = AnyYesRule | CountYesRule | ChoiceMapRule | ContainsAnyRule


@dataclass(frozen=True)
class Risk:
    """A named risk whose level is derived from rules applied to form answers."""

    id: str
    name: str
    description: str
    rules: tuple[RiskRule, ...]
    default_likelihood: str = "rare"
    default_consequence: str = "minor"


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
    """A safeguard whose presence is determined by a question answer."""

    id: str
    name: str
    question_id: str
    present_value: str
    effects: tuple[ControlEffect, ...]

    def presence_js(self) -> str:
        """JS expression evaluating to true/false for control presence."""
        qid = json.dumps(self.question_id)
        val = json.dumps(self.present_value)
        return (
            f"Array.isArray(this.answers[{qid}])"
            f" ? this.answers[{qid}].includes({val})"
            f" : this.answers[{qid}] === {val}"
        )


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
