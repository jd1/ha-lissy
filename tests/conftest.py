"""Test fixtures and path setup for the Lissy integration."""

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(__file__))
# Repo root so `import custom_components.lissy` works (HA integration discovery).
sys.path.insert(0, _ROOT)
# lissy source dir so the isolated scraper tests can `import api` directly.
sys.path.insert(0, os.path.join(_ROOT, "custom_components/lissy"))

# The pytest-homeassistant-custom-component plugin imports its own bundled
# `custom_components` (testing_config) at startup, shadowing ours. Make the repo
# copy discoverable by adding it to the package search path.
import custom_components  # noqa: E402

_OUR_CC = os.path.join(_ROOT, "custom_components")
if _OUR_CC not in custom_components.__path__:
    custom_components.__path__.append(_OUR_CC)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable the lissy custom integration for every test."""
    yield
