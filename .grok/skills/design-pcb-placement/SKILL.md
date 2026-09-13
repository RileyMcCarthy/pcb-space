---
name: design-pcb-placement
description: >
  Place a sourced, built schematic onto a courtyard-legal KiCad board using
  pcb-space place (CSS locks + KRT legalize). Use when the user asks to place
  parts, write a .place.py, lock connectors, run pcb-space place, or
  /design-pcb-placement. Do not use for schematic, routing, DFM, or Gerbers.
---

# Design PCB placement

Stop at a copper-free board whose locked poses match the `.place.py` and whose
unlocked parts are courtyard-legal. Do not open Pcbnew. Do not route. Do not
Gerber. Do not rewrite KiCadRoutingTools' `/plan-pcb-placement` skill — wrap it.

Tools: `pcb-space place` / `check` / `apply` / `silk`. Engine: KRT `place_seed`
(`KRT_HOME`, default `~/Downloads/KiCadRoutingTools`). Worked example:
`examples/c3_usb/`.

## 0. Inputs

You need a schematic that already passed `/design-pcb-schematic` (`pcb build` ✓,
pinned MPNs, body gates). Placement does not source parts.

Write `Board` size from the enclosure / USB-C + largest module, not from a guess
that the engine will “make it fit”.

## 1. Seed footprints once

```bash
pcb layout --no-open <board>.zen
```

That is seed-only: unique footprints, usually piled off-outline, **no Edge.Cuts**.
Never run `pcb layout` on a packed `placed/` board (it duplicates footprints).
Never treat `pcb layout` as a placer.

If the seed is missing a part the schematic has, re-run `pcb layout --no-open`
on the **seed** only.

## 2. `.place.py`

CSS names. Unitless = mm. Locked parts are `position: absolute`. Courtyard is
intrinsic size. `margin: auto` centers. `pcb-space` maps Zener instance names
(`J1`) to KiCad refs via footprint `Path` (`J1.TYPE_C_…`).

```python
Board(width=40, height=30, layers=2, stackup="jlcpcb_2l_1oz",
      pcb="layout/<name>/layout.kicad_pcb")

Place("J1", position="absolute", right=0, top=0, bottom=0,
      margin_top="auto", margin_bottom="auto", rotate=90, locked=True,
      reason="USB-C at board end")
```

- Connectors that mate through the enclosure: lock them. `right=0` + `left` unset
  is the **east** edge (centering uses `top=bottom=0`; do not call that north).
- Antenna / RF window: `Keepout(...)`, **not** a giant courtyard. KiCad MINI-1
  lands draw the RF keep-out on CrtYd (43×32 mm). Trim CrtYd to the datasheet
  body (13.2×16.6) + 0.25 mm or the module will not fit a 40×30 board.
- `NetReq` kinds compile geometry for step 3. Analog / switch_node stay
  `autoroute=False` — still declare them here.

Rejected: `z-index`, `flex`, `px`. `pcb layout` is not a CSS engine.

## 3. Place

```bash
pcb-space place <board>.place.py
pcb-space check <board>.place.py --pcb layout/<name>/placed/layout.kicad_pcb
```

`place` copies the seed into `placed/` (a second `.kicad_pro` beside the seed
makes `pcb layout` refuse the project), inserts `Edge.Cuts` from `Board` size,
locks CSS poses as `(locked yes)`, compiles a KRT floorplan-intent, runs
`place_seed --force --anchors-first`, then **`pcb-space silk`**: library refs
are 1 mm and will overlap on 0402 packing — silk sizes text from courtyard
(0.5–0.8 mm) and slots it off the body. File-locked parts must not move.

## 4. Sign-off (all required)

On the **copper-free** `placed/` board:

```bash
pcb-space check <board>.place.py --pcb layout/<name>/placed/layout.kicad_pcb
# KRT_HOME python:
python3 -X utf8 py_router/check_drc.py placed/layout.kicad_pcb --clearance 0.16
python3 -X utf8 py_tools/check_assembly.py placed/layout.kicad_pcb
python3 -X utf8 py_tools/check_floorplan.py placed/layout.kicad_pcb --intent placed/layout.intent.json
```

Pass only if:

- Unique footprint count equals `pcb build` component count
- 0 segments (still unrouted)
- Spec outline present (`Edge.Cuts` geometry, not just the layer table)
- Locked refs unmoved (`pcb-space check` ok)
- `check_drc` pad-pad **0**
- `check_assembly` blocking **0** (verdict buildable)
- KRT intent grade **0 errors** (declared edge-connector courtyard flush may
  count as budgeted `oob_count`; pad copper off-board must still be 0)

Fail (not “done”): Gerbers, `pcb dfm`, routing, `pcb layout` on `placed/`,
unlocked connectors, courtyard-as-antenna that is larger than the board.

After sign-off, stop. Routing is `/design-pcb-routing`.
