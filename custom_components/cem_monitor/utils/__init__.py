"""Utility modules for CEM Monitoring Integration."""

# Import from parent utils.py module (avoiding circular import)
import importlib.util
from pathlib import Path

# Load the parent utils.py module
utils_file = Path(__file__).parent.parent / "utils.py"
spec = importlib.util.spec_from_file_location("cem_utils_module", utils_file)
cem_utils_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cem_utils_module)

# Re-export functions from utils.py
get_int = cem_utils_module.get_int
get_str = cem_utils_module.get_str
get_str_nonempty = cem_utils_module.get_str_nonempty
slug_int = cem_utils_module.slug_int
slug_text = cem_utils_module.slug_text
ms_to_iso = cem_utils_module.ms_to_iso

# Import submodules
from . import discovery, retry
from .discovery import select_water_var_ids

# Re-export from submodules
from .retry import async_retry_with_backoff, is_401_error, is_retryable_error

__all__ = [
    # Functions from utils.py
    "get_int",
    "get_str",
    "get_str_nonempty",
    "slug_int",
    "slug_text",
    "ms_to_iso",
    # Submodules
    "retry",
    "discovery",
    # Functions from submodules
    "is_401_error",
    "is_retryable_error",
    "async_retry_with_backoff",
    "select_water_var_ids",
]
