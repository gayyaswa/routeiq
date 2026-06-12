import pytest
from langchain_core.runnables import RunnableLambda

from routeiq.insights import QueryParser
from routeiq.insights.prompts import QUERY_PARSER_PROMPT
from routeiq.insights.route_input import RouteInput


class _MockLLM:
    """Test double for a chat model — with_structured_output returns a fixed RouteInput."""

    def __init__(self, result: RouteInput):
        self._result = result

    def with_structured_output(self, schema):
        result = self._result
        return RunnableLambda(lambda _: result)


_VALID_RESULT = RouteInput(
    origin="Austin, TX",
    destination="San Antonio, TX",
    preferences=["historic"],
)

_EMPTY_RESULT = RouteInput(origin=None, destination=None, preferences=[])


@pytest.fixture
def parser():
    return QueryParser(QUERY_PARSER_PROMPT, _MockLLM(_VALID_RESULT))


@pytest.fixture
def empty_parser():
    return QueryParser(QUERY_PARSER_PROMPT, _MockLLM(_EMPTY_RESULT))


class TestQueryParserParse:
    def test_returns_dict(self, parser):
        result = parser.parse("Drive from Austin to San Antonio, show historic towns")
        assert isinstance(result, dict)

    def test_origin_extracted(self, parser):
        result = parser.parse("Drive from Austin to San Antonio")
        assert result["origin"] == "Austin, TX"

    def test_destination_extracted(self, parser):
        result = parser.parse("Drive from Austin to San Antonio")
        assert result["destination"] == "San Antonio, TX"

    def test_preferences_extracted(self, parser):
        result = parser.parse("Drive from Austin to San Antonio, show historic towns")
        assert result["preferences"] == ["historic"]

    def test_no_parse_error_key_on_success(self, parser):
        result = parser.parse("Drive from Austin to San Antonio")
        assert "_parse_error" not in result


class TestQueryParserNullFields:
    def test_null_origin_returned(self, empty_parser):
        result = empty_parser.parse("take me somewhere nice")
        assert result["origin"] is None

    def test_null_destination_returned(self, empty_parser):
        result = empty_parser.parse("take me somewhere nice")
        assert result["destination"] is None

    def test_empty_preferences_returned(self, empty_parser):
        result = empty_parser.parse("take me somewhere nice")
        assert result["preferences"] == []
