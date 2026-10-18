"""Safe initialization for the disposable synthetic demo runtime.

Render's free filesystem is ephemeral, so a fresh instance needs one complete database,
keyring and set of demo documents.  We build those in a temporary sibling directory and
rename it into place only after cryptographic verification succeeds.  Existing or partial
data is never reset here: complete data is reused, while partial/corrupt data fails loudly.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from .registry import Registry
from .seed import seed


REQUIRED_RUNTIME_FILES = (
    "dolil.db",
    "keys/keys.json",
    "demo/summary.json",
    "demo/qr.txt",
    "demo/deed_genuine.pdf",
    "demo/deed_altered.pdf",
)


def _has_entries(data_dir: Path) -> bool:
    return data_dir.exists() and any(data_dir.iterdir())


def validate_runtime(data_dir: Path) -> None:
    """Raise RuntimeError unless all files form one internally consistent seed."""
    missing = [name for name in REQUIRED_RUNTIME_FILES if not (data_dir / name).is_file()]
    if missing:
        raise RuntimeError(
            f"runtime at {data_dir} is partial; missing: {', '.join(missing)}. "
            "Refusing to delete or reseed it automatically."
        )

    reg = None
    try:
        reg = Registry(str(data_dir / "dolil.db"), str(data_dir / "keys"))
        qr = (data_dir / "demo" / "qr.txt").read_text("utf-8").strip()
        genuine = reg.verify(qr=qr, document=(data_dir / "demo" / "deed_genuine.pdf").read_bytes())
        altered = reg.verify(qr=qr, document=(data_dir / "demo" / "deed_altered.pdf").read_bytes())
        if genuine["verdict"] != "GENUINE_CURRENT" or altered["verdict"] != "ALTERED":
            raise RuntimeError("demo signatures, documents and database do not verify together")
    except Exception as exc:
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError(f"runtime at {data_dir} is corrupt or inconsistent: {exc}") from exc
    finally:
        if reg is not None:
            reg.close()


def initialize_runtime(data_dir: Path, *, n_deeds: int = 500) -> bool:
    """Create an empty runtime once; return True if created and False if reused."""
    data_dir = Path(data_dir)
    if _has_entries(data_dir):
        validate_runtime(data_dir)
        return False

    data_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{data_dir.name}-initializing-", dir=data_dir.parent))
    try:
        seed(temporary, n_deeds=n_deeds)
        validate_runtime(temporary)
        if data_dir.exists():
            # Only an empty directory reaches this branch; partial data was rejected above.
            data_dir.rmdir()
        temporary.replace(data_dir)
        return True
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
