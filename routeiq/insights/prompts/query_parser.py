from langchain_core.prompts import ChatPromptTemplate
from routeiq.insights.prompts.system import SYSTEM_PROMPT
from routeiq.insights.examples.query_parser_examples import FEW_SHOT_EXAMPLES

# V1 — baseline structured extraction with few-shot examples
QUERY_PARSER_PROMPT_V1 = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", """Extract the route intent from the query below.

Few-shot examples:
{examples}

Rules:
- Always include the US state abbreviation in origin and destination (e.g. "San Jose, CA" not "San Jose").
- If any field cannot be determined, set it to null.

Query: {query}"""),
])

# V2 — extracts activities and user_context in addition to route intent
QUERY_PARSER_PROMPT_V2 = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", """Extract the route intent from the query below.

Few-shot examples:
{examples}

Rules:
- Always include the US state abbreviation in origin and destination (e.g. "San Jose, CA" not "San Jose").
- If any field cannot be determined, set it to null or [].
- activities: extract specific physical activities (hiking, biking, swimming, kayaking, kids, picnic, rock climbing, etc.). Return [] if none mentioned.
- user_context: extract adjective phrases that describe the activity style (e.g. "scenic coastal hiking", "easy family trails"). Return "" if none.

Query: {query}"""),
])

QUERY_PARSER_PROMPT = QUERY_PARSER_PROMPT_V2  # active version
