"""Project-wide pytest safety defaults."""

from __future__ import annotations

import os


os.environ["VPB_ALLOW_BROWSER_OPEN"] = "0"
