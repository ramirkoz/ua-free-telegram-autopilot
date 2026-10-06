"""Clean V2 runtime.

This package is deliberately independent from the historical RC monkey-patch stack.
Historical RC builds are treated as behavioural specifications only; no ``rcXX`` module is imported
from V2.
"""

V2_SCHEMA_VERSION = 2
V2_VERSION = "2.0.0-rc109"

from .runtime_contracts import install_runtime_contracts
install_runtime_contracts()

from .operational_retention import install_operational_contracts
install_operational_contracts()

from .operational_finalizer import install_operational_finalizer
install_operational_finalizer()

# Same-version RC103 live hotfix: the first two RC103 operator builds proved that
# seven-day retention must not sit in the startup gate. Install this last so it
# replaces the startup wrapper added by the retention/finalizer layers while
# keeping their UI, supervisor and editorial contracts intact.
from .startup_background_hotfix import install_startup_background_hotfix
install_startup_background_hotfix()
