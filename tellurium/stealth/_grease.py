"""GREASE brand extraction from Browser.getVersion / navigator.userAgentData.brands.

GREASE tokens are RFC 8701-style "greasy" brand entries that Chrome adds to
userAgentData.brands to prevent servers from hard-coding a closed brand list.
The exact token is randomized across Chrome versions (e.g. 'Not_A Brand',
'Not?A_Brand', 'Not;A=Brand', '(Not;Browser)').
"""

from __future__ import annotations

_KNOWN_PRODUCT_BRANDS: frozenset[str] = frozenset(
    {
        "Chromium",
        "Google Chrome",
        "Microsoft Edge",
        "Opera",
        "Brave",
    }
)

_FALLBACK_BRAND = "Not_A Brand"
_FALLBACK_VERSION = "24"


def parse_grease_brands(brands: list[dict]) -> tuple[str, str]:
    """Return (brand, version) of the GREASE entry in the brands list.

    The GREASE entry is whichever entry is NOT a known product brand.
    Falls back to ('Not_A Brand', '24') if no non-product entry exists.
    """
    for entry in brands:
        brand = entry.get("brand", "")
        if brand and brand not in _KNOWN_PRODUCT_BRANDS:
            return brand, str(entry.get("version", _FALLBACK_VERSION))
    return _FALLBACK_BRAND, _FALLBACK_VERSION


def parse_product_version(product: str) -> str | None:
    """Extract the full version from a ``Browser.getVersion`` product string.

    ``"Chrome/153.0.8010.36"`` and ``"HeadlessChrome/153.0.8010.36"`` both
    yield ``"153.0.8010.36"``; anything else yields ``None``.
    """
    if not product or "/" not in product:
        return None
    version = product.rsplit("/", 1)[1].strip()
    parts = version.split(".")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        return version
    return None
