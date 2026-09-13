"""Shared fixtures. In CI, kicad-marked tests must run, not skip."""

from __future__ import annotations

import os
import shutil

import pytest

from pcb_space.fab import kicad_cli


def kicad_cli_or_skip():
    """Return kicad-cli, skip locally, fail in the CI kicad job."""
    cli = kicad_cli()
    if cli.exists() or shutil.which(str(cli)):
        return cli
    if os.environ.get("PCBSPACE_REQUIRE_KICAD") == "1":
        pytest.fail("kicad-cli required in this CI job (PCBSPACE_REQUIRE_KICAD=1)")
    pytest.skip("kicad-cli not installed")


@pytest.fixture
def require_kicad():
    return kicad_cli_or_skip()
