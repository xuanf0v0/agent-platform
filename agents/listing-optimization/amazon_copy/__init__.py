"""amazon_copy: Multi-agent Amazon listing copywriter."""

__version__ = "0.1.0"

from amazon_copy.orchestrator import (
    package_from_studio_state,
    run_pipeline,
    run_studio_pipeline,
)
from amazon_copy.orchestrator.state import StudioState
from amazon_copy.schemas.studio_output import OptimizationReport
from amazon_copy.studio import StudioService

__all__ = [
    "OptimizationReport",
    "StudioService",
    "StudioState",
    "__version__",
    "package_from_studio_state",
    "run_pipeline",
    "run_studio_pipeline",
]
