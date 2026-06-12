from __future__ import annotations
from langchain_core.language_models import BaseLanguageModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate


class FallbackChain:
    """Generates a helpful fallback response when the pipeline cannot complete a route (Chain pattern)."""

    def __init__(self, prompt: ChatPromptTemplate, llm: BaseLanguageModel) -> None:
        self._chain = prompt | llm | StrOutputParser()

    def generate(self, reason: str, query: str) -> str:
        return self._chain.invoke({"reason": reason, "query": query})
