import json
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class YesNoQuestion:
    """A yes/no radio-button question."""

    id: str
    text: str
    type: str = field(default="yes_no", init=False)


@dataclass(frozen=True)
class FreeTextQuestion:
    """A free-text textarea question."""

    id: str
    text: str
    type: str = field(default="free_text", init=False)


@dataclass(frozen=True)
class MultipleChoiceQuestion:
    """A single-select radio-button question with arbitrary options."""

    id: str
    text: str
    options: tuple[str, ...]
    type: str = field(default="multiple_choice", init=False)


@dataclass(frozen=True)
class MultipleSelectQuestion:
    """A multi-select checkbox question with arbitrary options."""

    id: str
    text: str
    options: tuple[str, ...]
    type: str = field(default="multiple_select", init=False)


Question = YesNoQuestion | FreeTextQuestion | MultipleChoiceQuestion | MultipleSelectQuestion


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


@dataclass(frozen=True)
class ChoiceMapRule:
    """Maps a multiple-choice answer to a risk level via a lookup dict."""

    question_id: str
    mapping: dict[str, str]

    def to_js(self) -> str:
        return f"{json.dumps(self.mapping)}[this.answers[{json.dumps(self.question_id)}]] || null"


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


RiskRule = AnyYesRule | CountYesRule | ChoiceMapRule | ContainsAnyRule


@dataclass(frozen=True)
class Risk:
    """A named risk whose level is derived from rules applied to form answers."""

    id: str
    name: str
    description: str
    rules: tuple[RiskRule, ...]
    default_level: str = "not_applicable"
