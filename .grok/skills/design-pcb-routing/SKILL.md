---
name: design-pcb-routing
description: >
  Route a courtyard-legal placed board with pcb-space route (KRT: USB pair,
  signals, then 2-layer GND pour). Use when the user asks to route copper,
  run pcb-space route, autoroute, or /design-pcb-routing. Do not use for
  schematic, placement, DFM, or Gerbers.
---

# Design PCB routing

Stop at copper that `check_connected` and copper `check_drc` can grade. Do not
open Pcbnew. Do not Gerber. Do not rewrite KiCadRoutingTools' `/plan-pcb-routing`
skill — wrap it.

Tools: `pcb-space route`. Engine: KRT (`KRT_HOME`). Input is the **placed**
board from `/design-pcb-placement`. Worked example: `examples/c3_usb/`.

## 0. Inputs

- Placement sign-off already passed (locked connectors, pad-pad 0, assembly blocking 0).
- Analog / switch-node nets are `NetReq(..., kind="analog"|"switch_node")` so they stay in `skip_autoroute`. Do not autoroute them.

## 1. Geometry the compiler owns

`pcb-space route` reads the `.place.py`:

- 2-layer: `F.Cu`/`B.Cu` only, layer costs 1.0/1.0, signals then GND pour on both sides, then finalize. True 90 Ω USB is **not** manufacturable on 1.6 mm 2-layer (loosely-coupled members want ~2 mm). The compiler clamps USB to a tightly-coupled 0.10/0.10 pair at the fab floor.
- 4-layer: pass `--impedance 90` on `route_diff`; pour `Board.planes` first.
- USB-C 0.5 mm pitch: first step is `qfn_fanout --escape-method underpad --allow-via-in-pad` on the locked east connector. If the land has overlapping pads (EasyEDA USB-C), fanout drops every via — that is a **footprint** defect, not a router knob.

## 2. Run

```bash
pcb-space route <board>.place.py
# uses layout/<name>/placed/layout.kicad_pcb when it exists
# writes layout/<name>/routed/layout.kicad_pcb
```

`--script-only` writes `routed/pcbspace_route.sh` without running.

## 3. Sign-off

```bash
pcb-space check <board>.place.py --pcb layout/<name>/routed/layout.kicad_pcb
python3 -X utf8 py_router/check_connected.py routed/layout.kicad_pcb
python3 -X utf8 py_router/check_drc.py routed/layout.kicad_pcb
```

Pass only if:

- Locked poses unmoved
- `check_connected` has no unjustified multi-pad opens
- `check_drc` is clean at the routed floor (quote the floor)

USB-C dual-orientation pads that stay open because the land's pads overlap each other are a CAD fix (`source check` / replace the EasyEDA land), not a rip-up retry.

Fail (not “done”): Gerbers, `pcb dfm`, moving locked parts to “make routing work” without a new placement sign-off.

After sign-off, stop. Fab packaging is `/design-pcb-fab`.
