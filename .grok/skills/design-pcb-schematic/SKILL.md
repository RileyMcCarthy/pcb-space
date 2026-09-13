---
name: design-pcb-schematic
description: >
  Design a KiCad-ready schematic in Zener using pcb-space source (LCSC/EasyEDA),
  datasheet pin-lock, pinned MPNs, and pcb build/bom gates. Use when the user
  asks to design a schematic, source parts, attach footprints, write a .zen
  board, pick LCSC/JLCPCB parts, or runs /design-pcb-schematic. Do not use for
  placement, routing, DFM, or Gerbers.
---

# Design PCB schematic

Stop at a netlist `pcb build` accepts and a BOM that lists **the MPNs you sourced**. Do not open Pcbnew. Do not run `pcb layout` or `pcb dfm` as schematic sign-off.

Tools: `pcb` (Zener), `pcb-space source` / `pcb-source`. Default fab is JLCPCB (`--fab jlcpcb`).

Worked example: pcb-space `examples/c3_usb/`.

## 0. Spec (write this first, in the board dir)

- Power tree: every rail, voltage, max current, what generates it
- Connectors: USB role (UFP/DFP), pin functions, which nets leave the board
- MCU/module: package, boot/download path, **strapping pins from the datasheet**
- What must not be autorouted later (analog, switch node) — note it; do not route it here

If any of those is unknown, stop and ask. Do not invent a pin map.

## 1. Source parts

Passives: stdlib generics only. Search LCSC, import `--kind generic`. Do not download a unique 0402 symbol.

```bash
pcb-space source search "100nF 0402" --fab jlcpcb
pcb-space source import C1525 --kind generic --manufacturer Samsung -o components
```

ICs/connectors/modules:

```bash
pcb-space source search ESP32-C3-MINI-1 --fab jlcpcb
pcb-space source import C2838502 --kind ic --manufacturer Espressif -o components
pcb-space source check components/Espressif/ESP32-C3-MINI-1-N4 --body 16.6x13.2
```

Prefer JLC **Basic** when the electrical part is the same. Record `lcsc` from the search hit in `SOURCE.json` (already written by import).

## 2. CAD gates (EasyEDA is not ground truth)

`source import` without `--footprint` pulls EasyEDA. Then:

1. `source check --body LxW` from the **datasheet package**, not the EasyEDA courtyard.
2. If body fails, attach a KiCad official land with `--footprint` and the same `--body`. Keep the EasyEDA **symbol** only when its pad numbers match the datasheet table **and** the KiCad land's pad numbers.
3. A file existing is not a pass. SHT40 1.5 mm on a 1.0 mm UDFN, and EasyEDA's ESP32-C3 module at 12.6×10.6 vs 16.6×13.2, are the same class of miss.

`Component(name=…)`: letters, digits, underscore only. No `.` (MPN `AP2112K-3.3` → `AP2112K_33TRG1`).

## 3. Pin-lock from the datasheet

Do not trust EasyEDA pin names for power/USB/straps. After import, diff the generated `.zen` `definition` against the datasheet pin table (package drawing, top view). Fix the `.zen` if they disagree. Cite the table in a comment on that module.

USB-C device (UFP), when present:

- Both orientations: D+ = A6 and B6, D− = A7 and B7
- CC1 and CC2 each 5.1 kΩ to GND
- Shell/mount pads to GND
- ESD on D+/D−/VBUS (e.g. USBLC6-2SC6) unless the user forbids it

MCU USB: use the module datasheet pad for D+/D− (ESP32-C3-MINI-1: IO19 = D+, IO18 = D−). Do not put a boot-strap GPIO on an LED or a pull-down.

LDO: Cin/Cout from the datasheet; EN must not float.

## 4. Board `.zen`

- `pcb.toml` with `[workspace] pcb-version = "0.4"` and `[board]`
- `Board(..., layout_path = "layout/<name>")` (this toolchain wants `layout_path`, not `path`)
- Every `Resistor` / `Capacitor` / `Led` gets `mpn=` **and** `manufacturer=` from the sourced reel. Omitting them lets `pcb bom` auto-pick a different MPN and can collapse a 16 V rail into a 10 V line.
- `Module("./components/…/*.zen")` for sourced ICs

## 5. Sign-off (all required)

```bash
pcb build <board>.zen          # must print ✓
pcb bom <board>.zen            # every row's MPN is one you imported
pcb-space source check <ic-pkg> --body …   # every IC land
```

Pass only if:

- `pcb build` succeeds
- BOM MPNs match `SOURCE.json` / the `mpn=` you wrote (not a substituted Murata/Yageo)
- Every IC `source check --body` is ok, or the miss is named and a replacement land is attached
- USB/straps/LDO EN match the datasheet notes in §0–3

Fail (not “done”): `pcb dfm` errors with no outline, `pcb layout`, Gerbers, unpinned generics, EasyEDA land that failed body check.

After sign-off, stop. Placement is `/design-pcb-placement`.
