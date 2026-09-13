"""Create a Zener + pcb-space project: pcb.toml, .zen, .place.py."""

from __future__ import annotations

import re
from pathlib import Path


_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


PCB_TOML = """\
[workspace]
pcb-version = "0.4"

[board]
name = "{name}"
path = "{name}.zen"
description = "Zener schematic; pcb-space places, routes, and fabs"
"""

ZEN = '''\
# ```pcb
# [workspace]
# pcb-version = "0.4"
# ```
# Schematic is Zener. Source parts with `pcb-space source`, then:
#   pcb-space build {name}.place.py
# Do not run `pcb layout` on placed/, routed/, or fab/.

VCC = Power("VCC")
GND = Ground("GND")

# Module("./components/…/*.zen") for sourced ICs.
# Pin every Resistor/Capacitor/Led with mpn= and manufacturer=.

Board(name = "{name}", layers = {layers}, layout_path = "layout/{name}")
'''

PLACE = '''\
# Spatial half. Schematic is {name}.zen (Zener).
# pcb-space build {name}.place.py
# Never run `pcb layout` on placed/, routed/, or fab/.

Board(
    width={width:g},
    height={height:g},
    layers={layers},
    stackup={stackup!r},
    pcb="layout/{name}/layout.kicad_pcb",
)

# Lock connectors that mate through the enclosure:
# Place("J1", position="absolute", right=0, top=0, bottom=0,
#       margin_top="auto", margin_bottom="auto", locked=True,
#       reason="USB-C at board end")

NetReq("VCC", "GND", kind="power", volts=3.3, amps=0.5)
'''

README_BOARD = """\
# {name}

Zener (`pcb`) is the schematic. pcb-space is the spatial compiler.

```bash
pcb-space build {name}.place.py
# already fabbed: no-op. Rebuild copper: pcb-space build --force
# stop early:     pcb-space build --upto place
```

Do **not** run `pcb layout` on `placed/`, `routed/`, or `fab/`. That duplicates footprints.
"""


def init_job(
    dest: Path,
    *,
    name: str | None = None,
    width: float = 40.0,
    height: float = 30.0,
    layers: int = 2,
    stackup: str = "jlcpcb_2l_1oz",
    force: bool = False,
) -> dict:
    dest = Path(dest).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    name = name or dest.name
    if not _NAME.match(name):
        raise ValueError(
            f"board name {name!r} must be letters, digits, underscore "
            "(Zener Component names reject '.')"
        )
    files = {
        dest / "pcb.toml": PCB_TOML.format(name=name),
        dest / f"{name}.zen": ZEN.format(name=name, layers=layers),
        dest / f"{name}.place.py": PLACE.format(
            name=name, width=width, height=height, layers=layers, stackup=stackup
        ),
        dest / "BOARD.md": README_BOARD.format(name=name),
    }
    written: list[str] = []
    skipped: list[str] = []
    for path, content in files.items():
        if path.exists() and not force:
            skipped.append(str(path))
            continue
        path.write_text(content)
        written.append(str(path))
    (dest / "components").mkdir(exist_ok=True)
    return {
        "root": str(dest),
        "name": name,
        "written": written,
        "skipped": skipped,
        "next": [
            f"pcb-space source search … --fab jlcpcb",
            f"pcb build {name}.zen",
            f"pcb-space seed {name}.place.py",
        ],
        "error": (
            None
            if written or not skipped
            else "files already exist; pass --force to overwrite"
        ),
    }
