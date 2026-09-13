---
name: design-pcb-fab
description: >
  Package a routed KiCad board for JLCPCB: Gerbers, drill, JLC BOM/CPL from
  SOURCE.json, fiducials, via-in-pad notes, kicad-cli DRC. Use when the user
  asks for fab files, Gerbers, BOM, CPL, DFM, JLCPCB upload, or
  /design-pcb-fab. Do not use for schematic, placement, or routing.
---

# Design PCB fab packaging

Stop at a **local** fab folder an agent can zip. Do not upload to JLCPCB. Do
not click Pcbnew. Wrap `kicad-cli` and `SOURCE.json`; do not rewrite KiCad.

Tools: `pcb-space build --upto fab` / `pcb-space fab`. Exporter: `kicad-cli`.
LCSC codes live in `components/**/SOURCE.json` — not in `pcb bom`. Worked
example: `examples/c3_usb/`.

## 0. Inputs

Routing sign-off from `/design-pcb-routing`: locks unmoved, `check_connected` fully connected, copper `check_drc` 0. Analog/switch unrouted by policy is OK only when those nets were declared `autoroute=False`.

## 1. What the compiler writes

```bash
pcb-space build <board>.place.py --upto fab
# uses committed routed/ if it exists (does not re-place / re-route)
# or: pcb-space fab <board>.place.py
# writes layout/<name>/fab/
```

| File | Role |
|---|---|
| `layout.kicad_pcb` | Copy of routed + 3 F.Cu fiducials (1 mm Cu / 2 mm mask) if missing, then `pcb-space silk` so gerber silk is readable |
| `gerbers/` | F/B Cu, paste, silk, mask, Edge.Cuts (`kicad-cli pcb export gerbers --check-zones`) |
| `*.drl` | Excellon PTH+NPTH, mm (`export drill --excellon-separate-th`) |
| `bom.csv` | `Comment,Designator,Footprint,LCSC Part #` — LCSC from SOURCE.json |
| `cpl.csv` | `Designator,Mid X,Mid Y,Rotation,Layer` mm, Layer Top/Bottom |
| `FAB_NOTES.md` | Via-in-pad census, fiducials, stackup, “do not order until notes are accepted” |
| `drc.json` | `kicad-cli pcb drc --refill-zones` |

## 2. Gates (all required)

Pass only if:

- `pcb-space check` still ok on the fab board (locked poses)
- Every BOM row has an LCSC code (no blank house MPNs)
- BOM designators ⊆ CPL designators
- `kicad-cli` DRC copper/connectivity errors = 0 at the routed floor (0.10 mm on 2-layer). Ignore silk, `via_dangling`, same-footprint pad-pad `shorting_items` (KiCad AABB on a rotated module; quote `check_drc.py` for shorts), and clearance that still meets the floor (KiCad Default/Power 0.16/0.20 must not re-grade 2-layer copper). Fab rewrites `.kicad_dru` so USB 0.10/0.10 is not graded at 0.13.
- ≥ 3 fiducials, ≥ 3.35 mm from Edge.Cuts, not on a courtyard
- Via-in-pad refs are **named** in `FAB_NOTES.md` (USB-C underpad needs filled+capped vias)

Fail (not “done”): uploading the zip, Gerbers from the unplaced seed, `pcb layout` on `fab/`, a BOM with empty LCSC.

`pcb dfm` on the `.zen` is advisory. It does not replace `kicad-cli` DRC on the routed copper.

## 3. Do not

- Send Gerbers to a fab from this skill
- Invent LCSC codes
- Resize the board for rails (JLC can add 5 mm rails at order time; we only add fiducials)
