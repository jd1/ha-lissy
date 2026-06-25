"""Add the lissy source dir to sys.path so api.py can be imported directly."""

import sys
import os

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../custom_components/lissy")
)
