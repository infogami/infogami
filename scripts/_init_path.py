"""Utility to setup sys.path."""

import sys
from pathlib import Path

INFOGAMI_PATH = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, INFOGAMI_PATH)
