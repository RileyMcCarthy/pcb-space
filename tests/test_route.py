from pathlib import Path

from pcb_space.compile import compile_design
from pcb_space.language import load_place_file
from pcb_space.route import copper_layers, krt_commands, via_size_drill

ROOT = Path(__file__).resolve().parents[1]


def test_copper_layers_2l():
    assert copper_layers(2) == ["F.Cu", "B.Cu"]
    assert "In1.Cu" not in copper_layers(2)


def test_c3_route_plan_is_two_layer():
    job = compile_design(load_place_file(ROOT / "examples" / "c3_usb" / "c3_usb.place.py"))
    pcb = ROOT / "examples" / "c3_usb" / "layout" / "c3_usb" / "placed" / "layout.kicad_pcb"
    cmds = krt_commands(job, pcb, work=Path("/tmp/routed-test"))
    flat = [" ".join(c) for c in cmds]
    joined = "\n".join(flat)
    assert "In1.Cu" not in joined
    assert "qfn_fanout.py" in joined
    assert "underpad" in joined
    assert "route_diff.py" in joined
    assert "USB_DP" in joined
    assert "--impedance" not in joined
    assert "route_planes.py" in joined
    assert "GND GND" in joined or any(
        c[c.index("--nets") + 1 : c.index("--plane-layers")] == ["GND", "GND"]
        for c in cmds
        if "--plane-layers" in c
    )
    assert joined.index("route.py") < joined.index("route_planes.py")
    last = cmds[-1]
    assert any(p.endswith("route.py") for p in last)


def test_sensitive_pass_is_front_copper_only():
    job = compile_design(load_place_file(ROOT / "examples" / "forma_pod.place.py"))
    cmds = krt_commands(job, Path("/tmp/placed.kicad_pcb"), work=Path("/tmp/routed-sens"))
    maze = next(c for c in cmds if "*" in c and any(p.endswith("route.py") for p in c))
    assert "!BOOST.BOOST_SW" in maze
    switch = next(
        c
        for c in cmds
        if "BOOST.BOOST_SW" in c
        and "*" not in c
        and any(p.endswith("route.py") for p in c)
    )
    analog = next(
        c
        for c in cmds
        if "CH[1-9]*" in c and "*" not in c and any(p.endswith("route.py") for p in c)
    )
    layers = switch[switch.index("--layers") + 1 : switch.index("--layer-costs")]
    assert layers == ["F.Cu"]
    assert "100000" in switch
    analog_layers = analog[analog.index("--layers") + 1 : analog.index("--layer-costs")]
    assert analog_layers == ["F.Cu"]
    assert cmds.index(analog) < cmds.index(maze)


def test_maze_forbids_via_in_pad_usb_fanout_keeps_it():
    job = compile_design(load_place_file(ROOT / "examples" / "c3_usb" / "c3_usb.place.py"))
    cmds = krt_commands(job, Path("/tmp/placed.kicad_pcb"), work=Path("/tmp/routed-vip"))
    fanout = next(c for c in cmds if any(str(p).endswith("qfn_fanout.py") for p in c))
    assert "--allow-via-in-pad" in fanout
    assert "--same-net-pad-clearance" not in fanout
    assert fanout[fanout.index("--via-size") + 1] == "0.25"
    maze = next(c for c in cmds if "*" in c and any(str(p).endswith("route.py") for p in c))
    assert maze[maze.index("--same-net-pad-clearance") + 1] == "0.10"
    assert maze[maze.index("--via-size") + 1] == "0.45"
    assert maze[maze.index("--via-drill") + 1] == "0.2"


def test_four_layer_planes_forbid_via_in_pad():
    job = compile_design(load_place_file(ROOT / "examples" / "buck_sw" / "buck_sw.place.py"))
    cmds = krt_commands(job, Path("/tmp/placed.kicad_pcb"), work=Path("/tmp/routed-4l"))
    planes = next(c for c in cmds if any(str(p).endswith("route_planes.py") for p in c))
    assert planes[planes.index("--same-net-pad-clearance") + 1] == "0.16"
    maze = next(c for c in cmds if "*" in c and any(str(p).endswith("route.py") for p in c))
    assert maze[maze.index("--same-net-pad-clearance") + 1] == "0.16"
    assert maze[maze.index("--via-size") + 1] == "0.45"
    taps = next(
        c
        for c in cmds
        if any(str(p).endswith("04_gnd_taps.kicad_pcb") for p in c)
    )
    assert taps[taps.index("--nets") + 1] == "GND"
    assert "--keep-input-copper" in taps
    d, h = via_size_drill(job)
    assert (d, h) == ("0.45", "0.2")