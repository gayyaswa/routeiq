from __future__ import annotations
import json
import re
from langchain_core.language_models import BaseLanguageModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from routeiq.insights.examples.query_parser_examples import FEW_SHOT_EXAMPLES


class QueryParser:
    """Parses a natural language route query into structured intent using Claude (Chain pattern)."""

    def __init__(self, prompt: ChatPromptTemplate, llm: BaseLanguageModel) -> None:
        self._chain = prompt | llm | StrOutputParser()
        self._examples = self._format_examples()

    def parse(self, query: str) -> dict:
        raw = self._chain.invoke({"examples": self._examples, "query": query})
        # Strip <think>...</think> blocks emitted by reasoning models (e.g. Qwen3)
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
        # Strip markdown code fences that some model versions wrap JSON in
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw.strip())
        # Extract the outermost {...} in case the model adds preamble or orphaned strings
        m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if m:
            raw = m.group(0)
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as e:
            return {"origin": None, "destination": None, "preferences": [], "_parse_error": str(e)}
        result.setdefault("origin", None)
        result.setdefault("destination", None)
        result.setdefault("preferences", [])
        return result

    def _format_examples(self) -> str:
        return "\n".join(
            f"Query: {ex['query']}\nOutput: {ex['output']}"
            for ex in FEW_SHOT_EXAMPLES
        )
