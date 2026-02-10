from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Visibility conditions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Equals:
    """True when a question's answer equals a specific value."""

    question_id: str
    value: str

    def to_js(self) -> str:
        return f"answers[{json.dumps(self.question_id)}] === {json.dumps(self.value)}"


@dataclass(frozen=True)
class Contains:
    """True when a multi-select answer includes a specific value."""

    question_id: str
    value: str

    def to_js(self) -> str:
        return f"(answers[{json.dumps(self.question_id)}] || []).includes({json.dumps(self.value)})"


@dataclass(frozen=True)
class All:
    """True when all child conditions are true (logical AND)."""

    conditions: tuple[Condition, ...]

    def to_js(self) -> str:
        return " && ".join(f"({c.to_js()})" for c in self.conditions)


@dataclass(frozen=True)
class Any:
    """True when any child condition is true (logical OR)."""

    conditions: tuple[Condition, ...]

    def to_js(self) -> str:
        return " || ".join(f"({c.to_js()})" for c in self.conditions)


@dataclass(frozen=True)
class Not:
    """Negation of a condition."""

    condition: Condition

    def to_js(self) -> str:
        return f"!({self.condition.to_js()})"


Condition = Equals | Contains | All | Any | Not


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class YesNoQuestion:
    """A yes/no radio-button question."""

    id: str
    text: str
    visible_when: Condition | None = None
    type: str = field(default="yes_no", init=False)


@dataclass(frozen=True)
class FreeTextQuestion:
    """A free-text textarea question."""

    id: str
    text: str
    visible_when: Condition | None = None
    type: str = field(default="free_text", init=False)


@dataclass(frozen=True)
class MultipleChoiceQuestion:
    """A single-select radio-button question with arbitrary options."""

    id: str
    text: str
    options: tuple[str, ...]
    visible_when: Condition | None = None
    type: str = field(default="multiple_choice", init=False)


@dataclass(frozen=True)
class MultipleSelectQuestion:
    """A multi-select checkbox question with arbitrary options."""

    id: str
    text: str
    options: tuple[str, ...]
    visible_when: Condition | None = None
    type: str = field(default="multiple_select", init=False)


Question = YesNoQuestion | FreeTextQuestion | MultipleChoiceQuestion | MultipleSelectQuestion


# ---------------------------------------------------------------------------
# Form structure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubSection:
    """A visual grouping of questions within a section."""

    title: str
    description: str
    questions: tuple[Question, ...]
    visible_when: Condition | None = None


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

RISK_LEVELS = ("not_applicable", "low", "medium", "high")


def _js_ids(ids: tuple[str, ...]) -> str:
    """Format a tuple of IDs as a JS array literal."""
    return json.dumps(list(ids))


@dataclass(frozen=True)
class AnyYesRule:
    """Evaluates to *level* if any of the given yes/no questions are 'yes'."""

    question_ids: tuple[str, ...]
    level: str

    def to_js(self) -> str:
        ids = _js_ids(self.question_ids)
        return f"{ids}.some(id => this.answers[id] === 'yes') ? {json.dumps(self.level)} : null"

    def referenced_question_ids(self) -> tuple[str, ...]:
        return self.question_ids


@dataclass(frozen=True)
class CountYesRule:
    """Evaluates to *level* if at least *threshold* yes/no questions are 'yes'."""

    question_ids: tuple[str, ...]
    threshold: int
    level: str

    def to_js(self) -> str:
        ids = _js_ids(self.question_ids)
        return (
            f"{ids}.filter(id => this.answers[id] === 'yes').length >= {self.threshold}"
            f" ? {json.dumps(self.level)} : null"
        )

    def referenced_question_ids(self) -> tuple[str, ...]:
        return self.question_ids


@dataclass(frozen=True)
class ChoiceMapRule:
    """Maps a multiple-choice answer to a risk level via a lookup dict."""

    question_id: str
    mapping: dict[str, str]

    def to_js(self) -> str:
        return f"{json.dumps(self.mapping)}[this.answers[{json.dumps(self.question_id)}]] || null"

    def referenced_question_ids(self) -> tuple[str, ...]:
        return (self.question_id,)


@dataclass(frozen=True)
class ContainsAnyRule:
    """Evaluates to *level* if a multi-select answer contains any of *values*."""

    question_id: str
    values: tuple[str, ...]
    level: str

    def to_js(self) -> str:
        vals = json.dumps(list(self.values))
        qid = json.dumps(self.question_id)
        return f"{vals}.some(v => (this.answers[{qid}] || []).includes(v)) ? {json.dumps(self.level)} : null"

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
    default_level: str = "not_applicable"
