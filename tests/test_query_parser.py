import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from routeiq.insights import QueryParser
from routeiq.insights.prompts import QUERY_PARSER_PROMPT

_VALID_JSON = '{"origin": "Austin, TX", "destination": "San Antonio, TX", "preferences": ["historic"]}'
_BAD_JSON = "I cannot parse this as a route request"


@pytest.fixture
def valid_llm():
    return RunnableLambda(lambda msgs: AIMessage(content=_VALID_JSON))


@pytest.fixture
def bad_llm():
    return RunnableLambda(lambda msgs: AIMessage(content=_BAD_JSON))


@pytest.fixture
def parser(valid_llm):
    return QueryParser(QUERY_PARSER_PROMPT, valid_llm)


@pytest.fixture
def bad_parser(bad_llm):
    return QueryParser(QUERY_PARSER_PROMPT, bad_llm)


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


class TestQueryParserMalformedJSON:
    def test_malformed_json_returns_parse_error_key(self, bad_parser):
        result = bad_parser.parse("take me somewhere nice")
        assert "_parse_error" in result

    def test_malformed_json_origin_is_none(self, bad_parser):
        result = bad_parser.parse("take me somewhere nice")
        assert result["origin"] is None

    def test_malformed_json_preferences_is_empty_list(self, bad_parser):
        result = bad_parser.parse("take me somewhere nice")
        assert result["preferences"] == []
