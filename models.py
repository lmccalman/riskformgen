from dataclasses import dataclass


@dataclass(frozen=True)
class YesNoQuestion:
    """A yes/no radio-button question for a form."""

    id: str
    text: str
