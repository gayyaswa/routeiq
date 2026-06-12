from langchain_core.prompts import ChatPromptTemplate
from routeiq.insights.prompts.system import SYSTEM_PROMPT

# V1 — handles no-POI, unparseable query, route-too-long edge cases
FALLBACK_PROMPT_V1 = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", """The route query could not be fully answered. Reason: {reason}

Query: {query}

Respond helpfully: explain what went wrong and suggest how the user can rephrase or adjust."""),
])

FALLBACK_PROMPT = FALLBACK_PROMPT_V1  # active version
