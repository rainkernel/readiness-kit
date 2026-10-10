"""The eight-area rubric: loading it, applying it to the run artefacts, rendering the scorecard."""

from readiness_kit.rubric.model import Rubric, load_rubric
from readiness_kit.rubric.score import Scorecard, score

__all__ = ["Rubric", "Scorecard", "load_rubric", "score"]
