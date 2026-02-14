"""Shared fixtures for riskformgen tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the project root is importable (models, render, etc. live at top level)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import (
    AnyYesRule,
    ChoiceMapRule,
    ContainsAnyRule,
    Control,
    ControlEffect,
    CountYesRule,
    Equals,
    FreeTextQuestion,
    MultipleChoiceQuestion,
    MultipleSelectQuestion,
    Risk,
    Section,
    SubSection,
    YesNoQuestion,
)


@pytest.fixture
def yes_no_q():
    return YesNoQuestion(id="q_yn", text="Is it risky?")


@pytest.fixture
def choice_q():
    return MultipleChoiceQuestion(
        id="q_mc", text="Pick one", options=("alpha", "beta", "gamma")
    )


@pytest.fixture
def multi_select_q():
    return MultipleSelectQuestion(
        id="q_ms", text="Pick many", options=("x", "y", "z")
    )


@pytest.fixture
def free_text_q():
    return FreeTextQuestion(id="q_ft", text="Describe the risk")


@pytest.fixture
def sample_questions(yes_no_q, choice_q, multi_select_q, free_text_q):
    return [yes_no_q, choice_q, multi_select_q, free_text_q]


@pytest.fixture
def sample_subsection(yes_no_q, choice_q):
    return SubSection(
        title="Basics",
        description="Basic questions",
        questions=(yes_no_q, choice_q),
    )


@pytest.fixture
def sample_section(sample_subsection):
    return Section(
        id="sec1",
        title="Section One",
        description="First section",
        subsections=(sample_subsection,),
    )


@pytest.fixture
def sample_sections(sample_section):
    return [sample_section]


@pytest.fixture
def sample_risk():
    return Risk(
        id="r1",
        name="Data Breach",
        description="Risk of data leakage",
        rules=(
            AnyYesRule(question_ids=("q_yn",), likelihood="likely"),
            CountYesRule(
                question_ids=("q_yn", "q_yn2"),
                threshold=2,
                consequence="major",
            ),
            ChoiceMapRule(
                question_id="q_mc",
                mapping={
                    "alpha": {"likelihood": "rare"},
                    "beta": {"likelihood": "likely", "consequence": "major"},
                },
            ),
            ContainsAnyRule(
                question_id="q_ms",
                values=("x", "y"),
                likelihood="possible",
                consequence="medium",
            ),
        ),
        default_likelihood="rare",
        default_consequence="minor",
    )


@pytest.fixture
def sample_control():
    return Control(
        id="ctrl1",
        name="Encryption enabled",
        question_id="q_yn",
        present_value="yes",
        effects=(
            ControlEffect(risk_id="r1", reduces_likelihood=True),
        ),
    )
