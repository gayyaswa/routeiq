from __future__ import annotations
import time
from typing import Any, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field

from routeiq.agent.agent_state import DayTripState
from routeiq.agent.tools import ALL_TOOLS
from routeiq.insights.prompts.day_trip_planner import DAY_TRIP_PLANNER_PROMPT
from routeiq.llm_factory import create_llm

# ── Output schemas ────────────────────────────────────────────────────────────

class ItineraryStop(BaseModel):
    """One stop in the day trip itinerary."""
    order: int
    name: str
    category: str
    lat: float
    lon: float
    arrival_time: str
    departure_time: str
    visit_duration_min: int
    why_visit: str = Field(description="One factual sentence from Wikipedia only.")
    visitor_quote: Optional[str] = Field(
        None, description="Single most vivid snippet prefixed with review_source name."
    )
    visitor_summary: Optional[str] = Field(
        None, description="1-2 sentence synthesis of overall visitor sentiment from all snippets."
    )
    activities: List[str] = Field(default_factory=list)
    rating: Optional[float] = None
    review_count: Optional[int] = None
    review_source: Optional[str] = None
    photo_urls: List[str] = Field(default_factory=list)
    image_url: Optional[str] = None
    hours: Optional[str] = None


class DayTripItinerary(BaseModel):
    """Full day trip itinerary produced by the agent."""
    city: str
    date: str
    total_hours: float
    stops: List[ItineraryStop]
    narrative: Optional[str] = None




def _execute_tool(tool_call: dict[str, Any]) -> ToolMessage:
    """Dispatch a single tool call and return the ToolMessage result."""
    name = tool_call["name"]
    args = tool_call["args"]
    tool_map = {t.name: t for t in ALL_TOOLS}
    if name not in tool_map:
        result = f"Unknown tool: {name}"
    else:
        try:
            result = tool_map[name].invoke(args)
        except Exception as exc:
            result = f"Tool error: {exc}"
    return ToolMessage(content=str(result), tool_call_id=tool_call["id"], name=name)


# ── Graph nodes ───────────────────────────────────────────────────────────────

def _plan(state: DayTripState) -> dict:
    """ReAct tool loop, then a structured-output call to extract the validated itinerary."""
    t0 = time.perf_counter()
    print(f"[dt_agent] _plan start city={state['city']}", flush=True)
    llm = create_llm()
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    # First pass: build messages from prompt template.
    # Re-plan pass: messages already contain conversation history + feedback HumanMessage.
    if not state["messages"]:
        messages = DAY_TRIP_PLANNER_PROMPT.format_messages(
            city=state["city"],
            preferences=", ".join(state["preferences"]) or "any",
            hours=state["time_budget_hours"],
            start_time=state["start_time"],
        )
    else:
        messages = list(state["messages"])

    # Phase 1 — ReAct loop: execute tools until the LLM stops calling them
    max_iterations = 12
    for iteration in range(max_iterations):
        response: AIMessage = llm_with_tools.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            print(f"[dt_agent] ReAct loop: iter={iteration} no tool calls → stopping", flush=True)
            break

        tool_names = [tc["name"] for tc in response.tool_calls]
        print(f"[dt_agent] ReAct loop: iter={iteration} tools={tool_names}", flush=True)
        for tc in response.tool_calls:
            messages.append(_execute_tool(tc))

    # Phase 2 — Structured extraction: the full conversation becomes context for a
    # validated Pydantic parse. This guarantees all fields are present and typed correctly.
    structured_llm = llm.with_structured_output(DayTripItinerary)
    extraction_prompt = (
        "Based on all the tool results above, produce the final day trip itinerary "
        "for " + state["city"] + ". Follow all faithfulness rules: visitor_quote from "
        "review snippets, visitor_summary synthesizing visitor sentiment, why_visit from "
        "Wikipedia only, activities grounded in Wikipedia and reviews."
    )
    itinerary: DayTripItinerary = structured_llm.invoke(
        messages + [HumanMessage(content=extraction_prompt)]
    )

    print(f"[dt_agent] _plan done in {time.perf_counter()-t0:.1f}s — {len((itinerary.model_dump().get('stops') or []))} stops", flush=True)
    return {"messages": messages, "draft_itinerary": itinerary.model_dump()}


def _review(state: DayTripState) -> Command:
    """Human-in-the-loop interrupt: surface draft to user and wait for approval."""
    decision: dict = interrupt(state["draft_itinerary"])

    if decision.get("approved"):
        return Command(goto="narrate", update={"approved": True})

    feedback = decision.get("feedback", "Please refine the itinerary.")
    return Command(
        goto="plan",
        update={
            "approved": False,
            "messages": [HumanMessage(content=f"Refine itinerary: {feedback}")],
        },
    )


def _narrate(state: DayTripState) -> dict:
    """Generate a warm 3–4 sentence narrative introduction for the day trip."""
    llm = create_llm()
    stop_names = [s["name"] for s in (state["draft_itinerary"] or {}).get("stops", [])][:3]
    prompt = (
        f"Write a warm, engaging 3–4 sentence narrative introducing this day trip to "
        f"{state['city']}. Mention these stops: {', '.join(stop_names)}. "
        "Do not use bullet points or markdown headers."
    )
    response = llm.invoke(list(state["messages"]) + [HumanMessage(content=prompt)])
    return {"narrative": response.content}


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_day_trip_graph() -> Any:
    """Build and compile the Day Trip Planner LangGraph state machine (Pipeline pattern)."""
    builder = StateGraph(DayTripState)

    builder.add_node("plan", _plan)
    builder.add_node("review", _review)
    builder.add_node("narrate", _narrate)

    builder.add_edge(START, "plan")
    builder.add_edge("plan", "review")
    builder.add_edge("narrate", "__end__")

    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer, interrupt_before=["review"])
