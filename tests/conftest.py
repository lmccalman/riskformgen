"""Shared fixtures for riskformgen tests."""

from __future__ import annotations

import pytest

from models import (
    BinaryQuestion,
    ConditionMapping,
    Control,
    ControlEffect,
    Detail,
    DetailQuestion,
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
        description="Risk of data leakage",
        conditions=(
            ConditionMapping(
                properties=("prop_a",),
                mode="all",
                likelihood="likely",
                consequence="major",
            ),
            ConditionMapping(
                properties=("prop_a", "prop_b"),
                mode="any",
                likelihood="possible",
                consequence="medium",
            ),
        ),
    )


@pytest.fixture
def sample_control():
    return Control(
        id="ctrl1",
        description="Encryption enabled",
        property="prop_a",
        effects=(ControlEffect(risk_id="r1"),),
    )


@pytest.fixture
def sample_detail():
    return Detail(
        id="det1",
        description="Outdoor context",
        properties=("prop_a",),
    )


@pytest.fixture
def detail_question(sample_detail):
    return DetailQuestion(
        id="q_det",
        text="Describe the outdoor activities.",
        detail_id=sample_detail.id,
        properties=sample_detail.properties,
    )
