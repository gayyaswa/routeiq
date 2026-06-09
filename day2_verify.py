"""Day 2 end-to-end verification: NL query → LangGraph pipeline → narrative."""
import os

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda

from routeiq.facade import RouteIQFacade


def _stub_llm():
    """Deterministic LLM stub used when ANTHROPIC_API_KEY is absent."""

    def respond(msgs):
        human_text = next(
            (m.content for m in msgs.messages if isinstance(m, HumanMessage)), ""
        )
        # query parser prompt contains "Extract the route intent"
        if "Extract the route intent" in human_text:
            return AIMessage(
                content='{"origin": "Austin, TX", "destination": "San Antonio, TX", "preferences": ["historic"]}'
            )
        # fallback prompt contains "could not be fully answered"
        if "could not be fully answered" in human_text:
            return AIMessage(
                content=(
                    "I couldn't find a route for your query. "
                    "Try specifying a clear origin and destination, "
                    "e.g. 'Drive from Austin to San Antonio, show historic towns'."
                )
            )
        # narrative prompt
        return AIMessage(
            content=(
                "This scenic drive from Austin to San Antonio winds through Texas Hill Country. "
                "Along the way you'll find storied missions and natural landmarks. "
                "Allow extra time to explore — these stops reward the curious traveler.\n\n"
                "Recommended stops:\n"
                "San Jose Mission | 2 min detour | UNESCO World Heritage mission complex\n"
                "Natural Bridge Caverns | 6 min detour | Stunning underground cave system"
            )
        )

    return RunnableLambda(respond)


def _print_state_summary(state: dict, label: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")

    if state.get("error"):
        print(f"  ERROR: {state['error']}")
        print(f"  Reason: {state.get('fallback_reason', '—')}")
    else:
        print(f"  Origin:       {state.get('origin')}")
        print(f"  Destination:  {state.get('destination')}")
        print(f"  Preferences:  {state.get('preferences')}")
        rr = state.get("route_result")
        if rr:
            print(f"  Route:        {rr.length_km:.1f} km  /  {rr.drive_time_min:.0f} min")
        pois = state.get("pois") or []
        top = state.get("top_pois") or []
        print(f"  POIs found:   {len(pois)}")
        print(f"  Top POIs:     {len(top)}")
        for sp in top:
            print(f"    • {sp.poi.name} ({sp.poi.category}) — {sp.detour_min:.0f} min detour")

    print(f"\n--- NARRATIVE ---\n{state.get('narrative', '(none)')}")


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if api_key:
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(model="claude-sonnet-4-6", api_key=api_key)
        print("Using real Claude (claude-sonnet-4-6)")
    else:
        llm = _stub_llm()
        print("ANTHROPIC_API_KEY not set — using deterministic stub LLM")

    print("\nStep 1: Building RouteIQFacade...")
    facade = RouteIQFacade(llm)
    print("  Done.")

    # ── happy path ──────────────────────────────────────────────────────────
    query = "Drive from Austin to San Antonio, show me historic towns and natural springs"
    print(f"\nStep 2: Running pipeline with query:\n  '{query}'")
    print("  (First run downloads OSM graph — ~2-5 min if not cached)")
    state = facade.run(query)
    _print_state_summary(state, "Happy path result")

    # ── fallback path ───────────────────────────────────────────────────────
    fallback_query = "take me somewhere interesting"
    print(f"\nStep 3: Testing fallback path:\n  '{fallback_query}'")
    fallback_state = facade.run(fallback_query)
    _print_state_summary(fallback_state, "Fallback result")

    print("\n\nDay 2 verification complete.")


if __name__ == "__main__":
    main()
