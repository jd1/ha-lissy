"""Unit tests for the curated library list and URL normalization."""

from __future__ import annotations

import json
import os
import re

from custom_components.lissy.libraries import (
    LIBRARIES,
    MANUAL_SLUG,
    SELECT_OPTIONS,
    library_for_url,
    normalize_portal_url,
)

_TRANSLATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "custom_components",
    "lissy",
    "translations",
)


def test_normalize_strips_scheme_and_trailing_slash():
    """Spelling drift (scheme, trailing slash) must not change the outcome."""
    assert normalize_portal_url("http://x/lissy/lissy.ly") == "x/lissy/lissy.ly"
    assert normalize_portal_url("https://x/lissy/lissy.ly/") == "x/lissy/lissy.ly"
    assert normalize_portal_url("https://X/LISSY/lissy.ly") == "x/LISSY/lissy.ly"


def test_normalize_keeps_path_and_drops_default_port():
    """The path discriminates biblis.de-hosted libraries; default ports go."""
    assert normalize_portal_url("http://h:80/lissy/lissy.ly") == "h/lissy/lissy.ly"
    assert normalize_portal_url("https://h:443/lissy/lissy.ly") == "h/lissy/lissy.ly"


def test_normalize_keeps_non_default_port():
    """An explicit unusual port is preserved so :2343 and :2443 stay distinct."""
    assert (
        normalize_portal_url("https://h:2443/lissy/lissy.ly") == "h:2443/lissy/lissy.ly"
    )


def test_normalize_falls_back_to_raw_url_without_host():
    """A path-only or empty input is normalized minimally instead of crashing."""
    assert normalize_portal_url("lissy/lissy.ly") == "lissy/lissy.ly"
    assert normalize_portal_url("") == ""


def test_library_for_url_known_and_unknown():
    """Listed portals resolve to their display name regardless of spelling."""
    assert library_for_url(LIBRARIES["aichach"]["url"]) == "Stadtbücherei Aichach"
    # Scheme or trailing-slash drift must still resolve.
    assert library_for_url(
        LIBRARIES["wangen"]["url"].replace("http", "https") + "/"
    ) == ("Stadtbücherei im Kornhaus, Wangen im Allgäu")
    assert library_for_url("http://not-listed.example/lissy/lissy.ly") is None
    assert library_for_url("") is None


def test_select_options_cover_libraries_and_manual():
    """Library slugs are sorted; the manual slug is pinned to the end."""
    assert SELECT_OPTIONS == [*sorted(LIBRARIES), MANUAL_SLUG]
    assert SELECT_OPTIONS[-1] == MANUAL_SLUG
    assert len(set(SELECT_OPTIONS)) == len(SELECT_OPTIONS)


def test_slugs_are_translation_key_safe():
    """Option values are valid hassfest translation keys ([a-z0-9_]+)."""
    pattern = re.compile(r"^[a-z0-9_]+$")
    for slug in SELECT_OPTIONS:
        assert pattern.match(slug), slug


def test_translations_cover_all_options():
    """Every option value has a label in both translation files."""
    for lang in ("en", "de"):
        with open(
            os.path.join(_TRANSLATIONS_DIR, f"{lang}.json"), encoding="utf-8"
        ) as f:
            options = json.load(f)["selector"]["library"]["options"]
        assert set(options) == set(SELECT_OPTIONS)
