"""Map Zener instance names (J1) to KiCad references (U3)."""

from __future__ import annotations

import re

from .sexp import board_footprint_spans, footprint_reference

_PATH = re.compile(r'\(property "Path" "([^"]+)"')


def footprint_path(block: str) -> str | None:
    m = _PATH.search(block)
    return m.group(1) if m else None


def ref_aliases(block: str) -> list[str]:
    """Names that may appear in a .place.py for this footprint."""
    names: list[str] = []
    ref = footprint_reference(block)
    if ref:
        names.append(ref)
    path = footprint_path(block)
    if path:
        names.append(path)
        head = path.split(".", 1)[0]
        if head and head not in names:
            names.append(head)
    return names


def build_alias_index(text: str) -> dict[str, str]:
    """alias → KiCad Reference. First writer wins on collisions."""
    idx: dict[str, str] = {}
    for start, end in board_footprint_spans(text):
        block = text[start:end]
        ref = footprint_reference(block)
        if not ref:
            continue
        for alias in ref_aliases(block):
            idx.setdefault(alias, ref)
    return idx


def resolve_ref(name: str, index: dict[str, str]) -> str | None:
    if name in index:
        return index[name]
    return None
