"""Load pure client modules without requiring a complete Home Assistant install."""

import sys
import types
from pathlib import Path

PACKAGE = "custom_components.ecoservice_waste_collection"
if PACKAGE not in sys.modules:
    module = types.ModuleType(PACKAGE)
    module.__path__ = [str(Path(__file__).parents[1] / "custom_components" / "ecoservice_waste_collection")]
    sys.modules[PACKAGE] = module
