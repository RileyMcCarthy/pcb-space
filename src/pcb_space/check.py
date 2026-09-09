"""Verify a KiCad board still matches compiled intent."""

from __future__ import annotations

from pathlib import Path

from .compile import CompiledJob
from .sexp import board_footprint_spans, footprint_at, footprint_reference


class CheckError(Exception):
    def __init__(self, failures: list[str]):
        self.failures = failures
        super().__init__("\n".join(failures))


def check_job(job: CompiledJob, pcb_path: Path, tol_mm: float = 0.05) -> list[str]:
    """Return a list of failure strings. Empty means pass."""
    pcb_path = Path(pcb_path)
    text = pcb_path.read_text()
    failures: list[str] = []

    by_ref = {}
    for start, end in board_footprint_spans(text):
        block = text[start:end]
        ref = footprint_reference(block)
        if ref:
            by_ref[ref] = block

    for place in job.places:
        block = by_ref.get(place.ref)
        if block is None:
            failures.append(f"missing footprint {place.ref}")
            continue
        at = footprint_at(block)
        if at is None:
            failures.append(f"{place.ref} has no (at …)")
            continue
        dx = abs(at[0] - place.at[0])
        dy = abs(at[1] - place.at[1])
        if dx > tol_mm or dy > tol_mm:
            failures.append(
                f"{place.ref} moved: have ({at[0]:.3f},{at[1]:.3f}) "
                f"want ({place.at[0]:.3f},{place.at[1]:.3f})"
            )
        if place.locked and "(locked yes)" not in block and "locked)" not in block:
            failures.append(f"{place.ref} is not locked")

    for ko in job.keepouts:
        if f'(name "{ko.name}")' not in text:
            failures.append(f"missing keepout zone {ko.name}")

    dru = pcb_path.with_suffix(".kicad_dru")
    if job.dru and not dru.exists():
        failures.append(f"missing {dru.name}")
    return failures


def check_or_raise(job: CompiledJob, pcb_path: Path) -> None:
    failures = check_job(job, pcb_path)
    if failures:
        raise CheckError(failures)
