"""Tests for graph layout computation."""

from __future__ import annotations

import pytest

from graph import compute_layout
from models import (
    ConditionMapping,
    Control,
    ControlEffect,
    Property,
    Risk,
)


@pytest.fixture
def root_properties() -> list[Property]:
    return [
        Property(id="prop_a", description="Property A"),
        Property(id="prop_b", description="Property B"),
    ]


@pytest.fixture
def derived_property() -> Property:
    return Property(id="prop_c", description="Property C", parents=("prop_a",))


@pytest.fixture
def sample_risk() -> Risk:
    return Risk(
        id="risk_1",
        description="Test risk",
        conditions=(
            ConditionMapping(
                properties=("prop_a",),
                mode="all",
                likelihood="likely",
                consequence="major",
            ),
        ),
    )


@pytest.fixture
def sample_control() -> Control:
    return Control(
        id="ctrl_1",
        description="Test control",
        property="prop_a",
        effects=(ControlEffect(risk_id="risk_1", reduces_likelihood=True),),
    )


class TestEmptyGraph:
    def test_empty_returns_empty_layout(self) -> None:
        layout = compute_layout([], [], [])
        assert layout.nodes == ()
        assert layout.edges == ()
        assert layout.width == 0
        assert layout.height == 0


class TestNodePlacement:
    def test_root_properties_placed(self, root_properties: list[Property]) -> None:
        layout = compute_layout(root_properties, [], [])
        assert len(layout.nodes) == 2
        node_ids = {n.id for n in layout.nodes}
        assert node_ids == {"prop_a", "prop_b"}

    def test_all_node_types_present(
        self,
        root_properties: list[Property],
        sample_risk: Risk,
        sample_control: Control,
    ) -> None:
        layout = compute_layout(root_properties, [sample_risk], [sample_control])
        kinds = {n.kind for n in layout.nodes}
        assert kinds == {"property", "risk", "control"}

    def test_derived_property_deeper_layer(
        self,
        root_properties: list[Property],
        derived_property: Property,
    ) -> None:
        props = [*root_properties, derived_property]
        layout = compute_layout(props, [], [])
        root_node = next(n for n in layout.nodes if n.id == "prop_a")
        derived_node = next(n for n in layout.nodes if n.id == "prop_c")
        # In left-to-right layout, derived should be further right
        assert derived_node.x > root_node.x

    def test_nodes_have_correct_labels(self, root_properties: list[Property]) -> None:
        layout = compute_layout(root_properties, [], [])
        labels = {n.id: n.label for n in layout.nodes}
        assert labels["prop_a"] == "Prop A"
        assert labels["prop_b"] == "Prop B"

    def test_nodes_have_dimensions(self, root_properties: list[Property]) -> None:
        layout = compute_layout(root_properties, [], [])
        for node in layout.nodes:
            assert node.width > 0
            assert node.height > 0


class TestEdges:
    def test_parent_edges(
        self,
        root_properties: list[Property],
        derived_property: Property,
    ) -> None:
        props = [*root_properties, derived_property]
        layout = compute_layout(props, [], [])
        parent_edges = [e for e in layout.edges if e.kind == "parent"]
        assert len(parent_edges) == 1
        assert parent_edges[0].source_id == "prop_a"
        assert parent_edges[0].target_id == "prop_c"

    def test_condition_edges(
        self,
        root_properties: list[Property],
        sample_risk: Risk,
    ) -> None:
        layout = compute_layout(root_properties, [sample_risk], [])
        cond_edges = [e for e in layout.edges if e.kind == "condition"]
        assert len(cond_edges) == 1
        assert cond_edges[0].source_id == "prop_a"
        assert cond_edges[0].target_id == "risk_1"

    def test_control_edges(
        self,
        root_properties: list[Property],
        sample_risk: Risk,
        sample_control: Control,
    ) -> None:
        layout = compute_layout(root_properties, [sample_risk], [sample_control])
        ctrl_in = [e for e in layout.edges if e.kind == "control_in"]
        ctrl_out = [e for e in layout.edges if e.kind == "control_out"]
        assert len(ctrl_in) == 1
        assert ctrl_in[0].source_id == "prop_a"
        assert ctrl_in[0].target_id == "ctrl_1"
        assert len(ctrl_out) == 1
        assert ctrl_out[0].source_id == "ctrl_1"
        assert ctrl_out[0].target_id == "risk_1"

    def test_edge_paths_are_valid_svg(
        self,
        root_properties: list[Property],
        derived_property: Property,
    ) -> None:
        props = [*root_properties, derived_property]
        layout = compute_layout(props, [], [])
        for edge in layout.edges:
            assert edge.path.startswith("M ")
            assert "L " in edge.path

    def test_deduplicated_condition_edges(self, root_properties: list[Property]) -> None:
        """A risk with the same property in multiple conditions should produce one edge."""
        risk = Risk(
            id="risk_dup",
            description="Dup risk",
            conditions=(
                ConditionMapping(
                    properties=("prop_a",), mode="all", likelihood="likely", consequence="major"
                ),
                ConditionMapping(
                    properties=("prop_a",),
                    mode="all",
                    likelihood="possible",
                    consequence="minor",
                ),
            ),
        )
        layout = compute_layout(root_properties, [risk], [])
        cond_edges = [e for e in layout.edges if e.kind == "condition"]
        assert len(cond_edges) == 1


class TestViewbox:
    def test_viewbox_contains_all_nodes(
        self,
        root_properties: list[Property],
        sample_risk: Risk,
        sample_control: Control,
    ) -> None:
        layout = compute_layout(root_properties, [sample_risk], [sample_control])
        parts = layout.viewbox.split()
        vb_x, vb_y, vb_w, vb_h = (float(p) for p in parts)

        for node in layout.nodes:
            assert node.x - node.width / 2 >= vb_x
            assert node.y - node.height / 2 >= vb_y
            assert node.x + node.width / 2 <= vb_x + vb_w
            assert node.y + node.height / 2 <= vb_y + vb_h

    def test_layout_dimensions_match_viewbox(self, root_properties: list[Property]) -> None:
        layout = compute_layout(root_properties, [], [])
        parts = layout.viewbox.split()
        vb_w, vb_h = float(parts[2]), float(parts[3])
        assert abs(layout.width - vb_w) < 0.01
        assert abs(layout.height - vb_h) < 0.01
