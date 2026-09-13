---
name: design-pcb-review
description: >
  Open a one-page HTML review of schematic, copper, and 3D (kicad-cli SVG/GLB).
  Use when the user asks to review the board, see layout and 3D together, or
  runs /design-pcb-review. Do not use for Gerbers or JLCPCB upload.
---

# Design PCB review

Stop at a local `review/index.html` the user can click through. Do not upload. Do not open Pcbnew.

```bash
pcb-space review <board>.place.py
# prefers layout/<name>/fab/layout.kicad_pcb, else routed/, else placed/
# writes layout/<name>/review/index.html and opens it
```

`--no-open` writes the page without launching a browser.

| Tab | Source |
|---|---|
| Schematic | `pcb apply schematic` on a copy (KiCad-10 box symbols from Zener pin maps) → `kicad-cli sch export svg/pdf`. `.zen` + netlist stay below. |
| Front / silk / back / both | `pcb-space silk` on a copy, then `kicad-cli pcb export svg`. Front is copper+silk (no paste/mask). Silk tab is F.SilkS only. |
| 3D | `kicad-cli pcb export glb` with tracks, pads, zones, silk, mask |
| BOM | `fab/bom.csv` when step 4 has run |

KiCad 3D libraries may not ship STEP for HRO USB-C or ESP32-C6-MINI — those parts show as empty pads. Copper SVGs still show routing.

Do not treat this page as fab sign-off. Fab packaging is `/design-pcb-fab`.
