from __future__ import annotations

import shutil
from pathlib import Path

from . import updater_helper as base
from .update_protocol import UpdateProtocol, UpdateRequest


def _safe_obtain_archive(request: UpdateRequest, target: Path) -> str:
    """Use Drive only when the mirrored overlay already matches the pinned SHA."""
    mirror = base._configured_mirror_dir()
    if mirror is not None:
        candidate = mirror / request.asset_name
        if candidate.is_file():
            try:
                if UpdateProtocol.sha256(candidate).casefold() == request.sha256.casefold():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(candidate, target)
                    return "drive-mirror"
            except OSError:
                pass
    base._download(request, target)
    return "github-release"


def main(argv: list[str] | None = None) -> int:
    # Reuse the thoroughly tested deterministic updater state machine; replace only
    # artifact acquisition so a partially synced Drive ZIP can never poison an
    # otherwise valid GitHub fallback.
    base._obtain_archive = _safe_obtain_archive
    return base.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
