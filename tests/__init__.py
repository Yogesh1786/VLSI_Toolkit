"""Test package. The tests always use a temporary SQLite store, never the real MongoDB."""

import os

os.environ["VT_STORE"] = "sqlite"
