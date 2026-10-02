"""Clean V2 runtime.

This package is deliberately independent from the historical RC monkey-patch stack.
Historical RC builds are treated as behavioural specifications only; no ``rcXX`` module is imported
from V2.
"""

V2_SCHEMA_VERSION = 2
V2_VERSION = "2.0.0-rc103"

from .runtime_contracts import install_runtime_contracts
install_runtime_contracts()

from .operational_retention import install_operational_contracts
install_operational_contracts()
