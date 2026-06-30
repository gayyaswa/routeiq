"""Session-wide test fixtures."""
import os
import pytest


@pytest.fixture(autouse=True, scope="session")
def _force_nebius_provider():
    """Force LLM_PROVIDER=nebius in tests so mocked with_structured_output is used.

    The Anthropic extraction path (_extract_itinerary_anthropic) calls llm.invoke()
    directly and parses raw JSON — it cannot be exercised with a MagicMock LLM.
    Tests validate agent graph logic, not provider-specific extraction mechanics.
    """
    os.environ.setdefault("LLM_PROVIDER", "nebius")
    yield
