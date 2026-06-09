from langchain_core.prompts import ChatPromptTemplate
from routeiq.insights.prompts.system import SYSTEM_PROMPT
from routeiq.insights.examples.query_parser_examples import FEW_SHOT_EXAMPLES

# V1 — baseline structured extraction with few-shot examples
QUERY_PARSER_PROMPT_V1 = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", """Extract the route intent from the query below.

Few-shot examples:
{examples}

Return JSON with keys: origin, destination, preferences (list of strings).
If any field cannot be determined, set it to null.

Query: {query}"""),
])

QUERY_PARSER_PROMPT = QUERY_PARSER_PROMPT_V1  # active version
