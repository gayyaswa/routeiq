from __future__ import annotations
from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts import ChatPromptTemplate
from routeiq.insights.examples.query_parser_examples import FEW_SHOT_EXAMPLES
from routeiq.insights.route_input import RouteInput


class QueryParser:
    """Parses a natural language route query into structured intent using Claude (Chain pattern)."""

    def __init__(self, prompt: ChatPromptTemplate, llm: BaseLanguageModel) -> None:
        self._chain = prompt | llm.with_structured_output(RouteInput)
        self._examples = self._format_examples()

    def parse(self, query: str) -> dict:
        try:
            result: RouteInput = self._chain.invoke({"examples": self._examples, "query": query})
            return result.model_dump()
        except Exception as e:
            return {"origin": None, "destination": None, "preferences": [], "_parse_error": str(e)}

    def _format_examples(self) -> str:
        return "\n".join(
            f"Query: {ex['query']}\nOutput: {ex['output']}"
            for ex in FEW_SHOT_EXAMPLES
        )
