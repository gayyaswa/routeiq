from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class RouteInput(BaseModel):
    """Structured route intent extracted from a natural language query (DTO pattern)."""

    origin: Optional[str] = Field(None, description="Starting location with US state abbreviation, e.g. 'San Francisco, CA'")
    destination: Optional[str] = Field(None, description="Ending location with US state abbreviation, e.g. 'Muir Woods, CA'")
    preferences: List[str] = Field(default_factory=list, description="Travel preferences mentioned, e.g. ['redwoods', 'coastal views']")
    activities: List[str] = Field(default_factory=list, description="Physical activities requested (hiking, biking, swimming, kids, kayaking, picnic, etc.)")
    user_context: str = Field("", description="Adjective phrases describing activity style, e.g. 'scenic coastal hiking'")
