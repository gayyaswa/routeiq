import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda

from routeiq.insights import FallbackChain
from routeiq.insights.prompts import FALLBACK_PROMPT

_FALLBACK_RESPONSE = "I couldn't process that request. Please provide a clear origin and destination."


@pytest.fixture
def mock_llm():
    return RunnableLambda(lambda msgs: AIMessage(content=_FALLBACK_RESPONSE))


@pytest.fixture
def chain(mock_llm):
    return FallbackChain(FALLBACK_PROMPT, mock_llm)


class TestFallbackChainGenerate:
    def test_returns_string(self, chain):
        result = chain.generate(reason="route_too_long", query="drive across the country")
        assert isinstance(result, str)

    def test_result_not_empty(self, chain):
        result = chain.generate(reason="route_too_long", query="drive across the country")
        assert len(result) > 0

    def test_reason_passed_to_prompt(self):
        captured = {}

        def capturing_llm(msgs):
            captured["human"] = next(
                (m.content for m in msgs.messages if isinstance(m, HumanMessage)), ""
            )
            return AIMessage(content="fallback response")

        chain = FallbackChain(FALLBACK_PROMPT, RunnableLambda(capturing_llm))
        chain.generate(reason="route_too_long", query="drive from NY to LA")
        assert "route_too_long" in captured["human"]
