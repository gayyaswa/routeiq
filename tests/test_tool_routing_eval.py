"""Unit tests for score_tool_routing — no API calls, mocked ToolMessages."""
import pytest
from unittest.mock import MagicMock

from eval.evaluators import score_tool_routing


def _tool_msg(name: str):
    """Minimal ToolMessage mock with just the .name attribute."""
    msg = MagicMock()
    msg.name = name
    # Make isinstance(msg, ToolMessage) return True via spec
    from langchain_core.messages import ToolMessage
    msg.__class__ = ToolMessage
    return msg


# ── Correct routing ──────────────────────────────────────────────────────────

def test_activities_set_select_pois_called_passes():
    msgs = [_tool_msg("select_pois_for_day"), _tool_msg("rate_pois")]
    result = score_tool_routing(["hiking"], msgs)
    assert result["routing_pass"] is True
    assert result["expected_tool"] == "select_pois_for_day"
    assert result["actual_first_poi_tool"] == "select_pois_for_day"


def test_multi_activities_select_pois_called_passes():
    msgs = [_tool_msg("select_pois_for_day"), _tool_msg("enrich_poi_details")]
    result = score_tool_routing(["hiking", "kids"], msgs)
    assert result["routing_pass"] is True


def test_no_activities_find_city_pois_called_passes():
    msgs = [_tool_msg("find_city_pois"), _tool_msg("rate_pois")]
    result = score_tool_routing([], msgs)
    assert result["routing_pass"] is True
    assert result["expected_tool"] == "find_city_pois"
    assert result["actual_first_poi_tool"] == "find_city_pois"


# ── Wrong tool called (the bug) ──────────────────────────────────────────────

def test_activities_set_but_find_city_pois_called_fails():
    """The bug: activities non-empty but iter=0 nudge forced find_city_pois."""
    msgs = [_tool_msg("find_city_pois"), _tool_msg("rate_pois")]
    result = score_tool_routing(["hiking"], msgs)
    assert result["routing_pass"] is False
    assert result["expected_tool"] == "select_pois_for_day"
    assert result["actual_first_poi_tool"] == "find_city_pois"


def test_no_activities_but_select_pois_called_fails():
    msgs = [_tool_msg("select_pois_for_day"), _tool_msg("rate_pois")]
    result = score_tool_routing([], msgs)
    assert result["routing_pass"] is False
    assert result["expected_tool"] == "find_city_pois"


# ── Edge cases ───────────────────────────────────────────────────────────────

def test_no_poi_tool_called_at_all_fails():
    msgs = [_tool_msg("rate_pois"), _tool_msg("enrich_poi_details")]
    result = score_tool_routing(["hiking"], msgs)
    assert result["routing_pass"] is False
    assert result["actual_first_poi_tool"] == "none"


def test_empty_tool_messages_fails():
    result = score_tool_routing(["hiking"], [])
    assert result["routing_pass"] is False
    assert result["actual_first_poi_tool"] == "none"


def test_only_first_poi_tool_matters_not_subsequent():
    """select_pois_for_day first, then find_city_pois — routing passes if first is correct."""
    msgs = [
        _tool_msg("select_pois_for_day"),
        _tool_msg("find_city_pois"),  # shouldn't matter
        _tool_msg("rate_pois"),
    ]
    result = score_tool_routing(["swimming"], msgs)
    assert result["routing_pass"] is True
    assert result["actual_first_poi_tool"] == "select_pois_for_day"


def test_non_poi_tools_before_poi_tool_are_ignored():
    """Non-POI tools (rate_pois, enrich_poi_details) before the first POI call don't count."""
    msgs = [
        _tool_msg("estimate_visit_duration"),
        _tool_msg("rate_pois"),
        _tool_msg("select_pois_for_day"),
    ]
    result = score_tool_routing(["biking"], msgs)
    assert result["routing_pass"] is True
    assert result["actual_first_poi_tool"] == "select_pois_for_day"


def test_routing_with_coastal_hiking_case():
    """Regression: the exact SF coastal hiking scenario that triggered the bug."""
    msgs = [_tool_msg("select_pois_for_day"), _tool_msg("rate_pois"), _tool_msg("enrich_poi_details")]
    result = score_tool_routing(["hiking", "kids"], msgs)
    assert result["routing_pass"] is True


def test_empty_activities_list_expects_find_city_pois():
    """Vacuous case: empty list (not None) still routes to find_city_pois."""
    msgs = [_tool_msg("find_city_pois")]
    result = score_tool_routing([], msgs)
    assert result["routing_pass"] is True
    assert result["expected_tool"] == "find_city_pois"
