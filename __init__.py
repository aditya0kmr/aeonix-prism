"""
ÆONIX PRISM Sovereign Intelligence Architecture
"""
import sys
import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_BASE_DIR)

for p in [_BASE_DIR, _PARENT_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)
