"""LCSC / JLCPCB parts search via the public jlcsearch API. No API key."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

JLCSEARCH = "https://jlcsearch.tscircuit.com/api/search"
USER_AGENT = "pcb-space/0.3 (+https://github.com/RileyMcCarthy/pcb-space)"


@dataclass
class LcscHit:
    mpn: str
    lcsc: str
    package: str
    description: str
    stock: int
    price_usd: float | None
    basic: bool
    preferred: bool

    def to_dict(self) -> dict:
        return {
            "vendor": "lcsc",
            "mpn": self.mpn,
            "lcsc": self.lcsc,
            "package": self.package,
            "description": self.description,
            "stock": self.stock,
            "price_usd": self.price_usd,
            "jlc_basic": self.basic,
            "jlc_preferred": self.preferred,
        }


def search_lcsc(query: str, limit: int = 10, opener=None) -> list[LcscHit]:
    """Search LCSC. `opener` is urlopen for tests."""
    url = JLCSEARCH + "?" + urllib.parse.urlencode({"q": query, "limit": int(limit)})
    open_fn = opener or urllib.request.urlopen
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with open_fn(req, timeout=20) as resp:
            raw = resp.read()
    except urllib.error.URLError as e:
        raise RuntimeError(f"LCSC search failed: {e}") from e
    data = json.loads(raw.decode() if isinstance(raw, (bytes, bytearray)) else raw)
    hits = []
    for row in data.get("components") or []:
        lcsc_n = row.get("lcsc")
        lcsc = f"C{lcsc_n}" if not str(lcsc_n).upper().startswith("C") else str(lcsc_n)
        hits.append(
            LcscHit(
                mpn=str(row.get("mfr") or ""),
                lcsc=lcsc,
                package=str(row.get("package") or ""),
                description=str(row.get("description") or ""),
                stock=int(row.get("stock") or 0),
                price_usd=float(row["price"]) if row.get("price") is not None else None,
                basic=bool(row.get("is_basic")),
                preferred=bool(row.get("is_preferred")),
            )
        )
    return hits
