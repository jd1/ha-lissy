"""Curated list of Lissy libraries for the config flow dropdown.

Every entry was verified by fetching ``<url>?pg=bnrlogin`` and finding the
login markers LissyClient matches on (``c=``, ``mgcnum=``). Libraries from
lissy_tr.htm that are deliberately absent:

* Forst (biblis.de/for) — LISSY, but was in its scheduled backup window on
  every check; re-verify and add when it is up again.
* Heidenheim (lissy.bibliothek-heidenheim.de) — LISSY, but no vhost is
  configured for the domain at the moment; likewise re-verify and add.

Option values are translation-key-safe slugs (lowercase, digits, underscore)
so they can be used as keys under ``selector.library.options`` in the
translation files; the display names live exclusively in the translations.
"""

from __future__ import annotations

from typing import Final, TypedDict
from urllib.parse import urlsplit


class Library(TypedDict):
    """A Lissy library: display name (German) and verified portal base_url."""

    name: str
    url: str


LIBRARIES: Final[dict[str, Library]] = {
    "aichach": Library(
        name="Stadtbücherei Aichach",
        url="https://lissy.stadtbuecherei-aichach.de/lissy/lissy.ly",
    ),
    "aidlingen": Library(
        name="Ortsbücherei Aidlingen",
        url="https://lissy.buecherei-aidlingen.de/lissy/lissy.ly",
    ),
    "auerbach": Library(
        name="Stadtbibliothek Auerbach",
        url="https://lissy.bibliothek-auerbach.de/lissy/lissy.ly",
    ),
    "bad_saulgau": Library(
        name="Stadtbücherei Bad Saulgau",
        url="https://lissy.bad-saulgau.de/lissy/lissy.ly",
    ),
    "bad_waldsee": Library(
        name="Stadtbücherei Bad Waldsee",
        url="https://gobooks.bad-waldsee.de/lissy/lissy.ly",
    ),
    "biblis_blaustein": Library(
        name="Stadtbücherei Blaustein",
        url="https://biblis.de/bls/lissy/lissy.ly",
    ),
    "biblis_gerstetten": Library(
        name="Bibliothek Gerstetten",
        url="https://biblis.de/ger/lissy/lissy.ly",
    ),
    "biblis_sontheim": Library(
        name="Ortsbücherei Sontheim/Brz.",
        url="https://biblis.de/son/lissy/lissy.ly",
    ),
    "blaubeuren": Library(
        name="Stadtbücherei Blaubeuren",
        url="http://katalog.stadtbuecherei-blaubeuren.de/lissy/lissy.ly",
    ),
    "dossenheim": Library(
        name="Gemeindebücherei Dossenheim",
        url="https://lissy.buecherei-dossenheim.de/lissy/lissy.ly",
    ),
    "ehingen": Library(
        name="Stadtbücherei Ehingen",
        url="http://webopac.ehingen.de/lissy/lissy.ly",
    ),
    "giengen": Library(
        name="Stadtbibliothek Giengen",
        url="https://lissy-giengen.de/lissy/lissy.ly",
    ),
    "langenargen": Library(
        name="Bücherei im Münzhof, Langenargen",
        url="https://www.buecherei-langenargen.de/lissy/lissy.ly",
    ),
    "leutkirch": Library(
        name="Stadtbibliothek Leutkirch",
        url="https://bibliothek.leutkirch.de/lissy/lissy.ly",
    ),
    "meersburg": Library(
        name="Stadtbücherei Meersburg",
        url="https://lissy.meersburg.de/lissy/lissy.ly",
    ),
    "passau": Library(
        name="Europabücherei Passau",
        url="https://buecherei.passau.de/lissy/lissy.ly",
    ),
    "schelklingen": Library(
        name="Stadtbücherei Schelklingen",
        url="http://lissy.stadtbuecherei-schelklingen.de/lissy/lissy.ly",
    ),
    "schwaebisch_gmuend": Library(
        name="Stadtbibliothek Schwäbisch Gmünd",
        url="http://stb.schwaebisch-gmuend.de/lissy/lissy.ly",
    ),
    "straubenhardt": Library(
        name="Gemeindebibliothek Straubenhardt",
        url="https://lissy.straubenhardt.de/lissy/lissy.ly",
    ),
    "tettnang": Library(
        name="Stadtbücherei Tettnang",
        url="https://lissy.stadtbuecherei-tettnang.de/lissy/lissy.ly",
    ),
    "waldenbuch": Library(
        name="Stadtbücherei Waldenbuch",
        url="https://lissy.stadtbuecherei-waldenbuch.de/lissy/lissy.ly",
    ),
    "wangen": Library(
        name="Stadtbücherei im Kornhaus, Wangen im Allgäu",
        url="http://lissy.buecherei-wangen.de/lissy/lissy.ly",
    ),
}


MANUAL_SLUG: Final = "manual"

SELECT_OPTIONS: Final[list[str]] = [*sorted(LIBRARIES), MANUAL_SLUG]


def normalize_portal_url(url: str) -> str:
    """Return a scheme-free canonical portal URL.

    The host (already lowercased by ``urlsplit``) is kept together with the
    path, while the scheme and trailing slash are dropped so spelling drift
    (``http`` vs ``https``, a trailing ``/``) cannot spawn a duplicate of
    the same account. The path is kept: several portals share one host
    (biblis.de serves Blaustein, Sontheim, Gerstetten at
    ``/<lib>/lissy/lissy.ly``), so the host alone does not discriminate.
    """
    parts = urlsplit(url)
    host = parts.hostname
    if not host:
        return url.rstrip("/")
    try:
        port = parts.port
    except ValueError:
        port = None
    default_port = {"https": 443, "http": 80}.get(parts.scheme)
    if port and port != default_port:
        return f"{host}:{port}{parts.path.rstrip('/')}"
    return f"{host}{parts.path.rstrip('/')}"


_LIBRARY_BY_URL: Final[dict[str, str]] = {
    normalize_portal_url(library["url"]): library["name"]
    for library in LIBRARIES.values()
}


def library_for_url(base_url: str) -> str | None:
    """Return the display name of a listed library, else None."""
    return _LIBRARY_BY_URL.get(normalize_portal_url(base_url))
