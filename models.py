from dataclasses import dataclass, field


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
