"""Shared fixtures for riskformgen tests."""

from __future__ import annotations

import pytest

from models import (
    AnyYesRule,
    BinaryQuestion,
    ChoiceMapRule,
    ContainsAnyRule,
    Control,
    ControlEffect,
    CountYesRule,
    Property,
    Risk,
    Section,
    SubSection,
)


@pytest.fixture
def binary_q():
    return BinaryQuestion(id="q_bin", text="Is it risky?", properties=("prop_a",))


@pytest.fixture
def binary_q2():
    return BinaryQuestion(id="q_bin2", text="Is it dangerous?", properties=("prop_b",))


@pytest.fixture
def sample_questions(binary_q, binary_q2):
    return [binary_q, binary_q2]


@pytest.fixture
def sample_subsection(binary_q, binary_q2):
    return SubSection(
        title="Basics",
        description="Basic questions",
        questions=(binary_q, binary_q2),
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
def sample_properties():
    return [
        Property(id="prop_a", description="Property A"),
        Property(id="prop_b", description="Property B", parents=("prop_a",)),
    ]


@pytest.fixture
def sample_risk():
    return Risk(
        id="r1",
        name="Data Breach",
        description="Risk of data leakage",
        rules=(
            AnyYesRule(question_ids=("q_bin",), likelihood="likely"),
            CountYesRule(
                question_ids=("q_bin", "q_bin2"),
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
        question_id="q_bin",
        present_value="yes",
        effects=(ControlEffect(risk_id="r1", reduces_likelihood=True),),
    )
