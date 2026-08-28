#!/usr/bin/env python3
"""CLI wrapper for the packaged Cortex Bridge storage guard."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "console"))

from storage_guard import (  # noqa: E402,F401
    DISKUTIL,
    HDIUTIL,
    EncryptedImageProbe,
    StorageIdentityProbe,
    VolumeProbe,
    check_required_storage,
    configured_bootstrap,
    main,
    probe_encrypted_image,
    probe_storage_identity,
    probe_volume,
)


if __name__ == "__main__":
    raise SystemExit(main())
