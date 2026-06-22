from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from routeiq.graph.poi import POI


@dataclass
class ClassifiedPOI:
    """A POI annotated with which activities it supports (dataclass)."""

    poi: POI
    matched_activities: list[str] = field(default_factory=list)
    activity_evidence: str | None = None    # top snippet from classifier source
    activity_rank_score: float = 0.0        # set by ActivityRanker; 0 = unranked


class ActivityClassifier(ABC):
    """Classifies which activities are supported at each POI (Strategy pattern)."""

    @abstractmethod
    def classify_batch(
        self,
        city: str,
        pois: list[POI],
        activities: list[str],
    ) -> list[ClassifiedPOI]:
        """Return every input POI as ClassifiedPOI; unmatched get matched_activities=[]."""
        ...
