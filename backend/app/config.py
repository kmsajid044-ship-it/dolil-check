import os
from pathlib import Path

# Runtime data (database + office keys). Never commit this folder.
DATA_DIR = Path(os.environ.get("DOLIL_DATA", Path(__file__).resolve().parents[2] / "data" / "runtime"))

# Invented offices for the prototype: one sub-registry, one AC Land office.
DEFAULT_OFFICES = {"SRO-NDP": "sub_registry", "ACL-NDP": "ac_land"}
