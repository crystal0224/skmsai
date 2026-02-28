"""Visualization Data Transforms 테스트.

PR-051: AntV 차트용 타임라인, 네트워크, 산키 데이터 구조 검증.
"""
from __future__ import annotations

from scripts.lib.content_studio.viz_data import (
    build_network_data,
    build_sankey_data,
    build_timeline_data,
)


# ===================================================================
# build_timeline_data
# ===================================================================


class TestBuildTimelineData:
    def test_structure(self):
        result = build_timeline_data()
        assert "chart_type" in result
        assert "title" in result
        assert "data" in result
        assert result["chart_type"] == "timeline"

    def test_12_editions(self):
        result = build_timeline_data()
        assert len(result["data"]) == 12

    def test_years_ascending(self):
        result = build_timeline_data()
        years = [entry["year"] for entry in result["data"]]
        assert years == sorted(years)

    def test_major_editions(self):
        result = build_timeline_data()
        major_entries = [
            entry for entry in result["data"] if entry["category"] == "major"
        ]
        major_years = {entry["year"] for entry in major_entries}
        assert 1998 in major_years
        assert 2020 in major_years

    def test_first_edition_is_foundation(self):
        result = build_timeline_data()
        first = result["data"][0]
        assert first["year"] == 1979
        assert first["category"] == "foundation"

    def test_all_entries_have_required_keys(self):
        result = build_timeline_data()
        for entry in result["data"]:
            assert "year" in entry
            assert "edition" in entry
            assert "label" in entry
            assert "category" in entry


# ===================================================================
# build_network_data
# ===================================================================


class TestBuildNetworkData:
    def test_structure(self):
        result = build_network_data()
        assert "chart_type" in result
        assert "nodes" in result
        assert "edges" in result
        assert result["chart_type"] == "network"

    def test_15_nodes(self):
        result = build_network_data()
        assert len(result["nodes"]) == 15

    def test_static_category(self):
        result = build_network_data()
        static_nodes = [n for n in result["nodes"] if n["category"] == "static"]
        assert len(static_nodes) == 10

    def test_dynamic_category(self):
        result = build_network_data()
        dynamic_nodes = [n for n in result["nodes"] if n["category"] == "dynamic"]
        assert len(dynamic_nodes) == 5

    def test_edges_reference_valid_nodes(self):
        result = build_network_data()
        node_ids = {n["id"] for n in result["nodes"]}
        for edge in result["edges"]:
            assert edge["source"] in node_ids, f"Invalid source: {edge['source']}"
            assert edge["target"] in node_ids, f"Invalid target: {edge['target']}"

    def test_edges_have_weight(self):
        result = build_network_data()
        for edge in result["edges"]:
            assert "weight" in edge
            assert isinstance(edge["weight"], int)
            assert edge["weight"] > 0


# ===================================================================
# build_sankey_data
# ===================================================================


class TestBuildSankeyData:
    def test_structure(self):
        result = build_sankey_data()
        assert "chart_type" in result
        assert "nodes" in result
        assert "links" in result
        assert result["chart_type"] == "sankey"

    def test_links_reference_valid_nodes(self):
        result = build_sankey_data()
        node_ids = {n["id"] for n in result["nodes"]}
        for link in result["links"]:
            assert link["source"] in node_ids, f"Invalid source: {link['source']}"
            assert link["target"] in node_ids, f"Invalid target: {link['target']}"

    def test_evolution_statuses(self):
        result = build_sankey_data()
        valid_statuses = {"evolved", "renamed", "maintained"}
        for link in result["links"]:
            assert "status" in link
            assert link["status"] in valid_statuses, f"Invalid status: {link['status']}"

    def test_links_have_value(self):
        result = build_sankey_data()
        for link in result["links"]:
            assert "value" in link
            assert isinstance(link["value"], int)
            assert link["value"] > 0

    def test_title(self):
        result = build_sankey_data()
        assert result["title"] == "SKMS 개념 진화"
