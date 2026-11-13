"""Gear, belt, Geneva, cam, and sewing-machine families move as their geometry says."""

import math

import numpy as np
import numpy.typing as npt
from orrery_kinematics import Simulation, Solver
from orrery_lab.families import family
from orrery_lab.families.drives import CamProfile
from orrery_lab.sampling import Sample, generate

STEP = math.tau / 180


def sweep(sample: Sample) -> tuple[Solver, Simulation]:
    solver = Solver(sample.graph_json())
    drive = np.zeros(solver.driver_count)
    drawn = solver.assemble(drive)
    low, high = sample.built.drive_range
    start = solver.simulate(0, drive, 0.0, low, STEP, seed=drawn).states[-1] if low else drawn
    return solver, solver.simulate(0, drive, low, high, STEP, seed=start)


def track(solver: Solver, sim: Simulation, body: str, point: str) -> npt.NDArray[np.float64]:
    return sim.points[:, solver.point_names.index((body, point)), :2]


def turning(
    solver: Solver, sim: Simulation, body: str, point: str, center: tuple[str, str]
) -> npt.NDArray[np.float64]:
    """The angle a point turns through about a center, unwrapped, from the first sample."""
    d = track(solver, sim, body, point) - track(solver, sim, *center)
    angle = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    return angle - angle[0]


def test_gear_trains_turn_at_their_tooth_ratios() -> None:
    for seed in range(6):
        sample = generate(family("gear-train"), seed)
        solver, sim = sweep(sample)
        gears = [b for b in sample.built.document["bodies"] if b["kind"] == "gear"]
        expected = sim.drive - sim.drive[0]
        for i, gear in enumerate(gears):
            turned = turning(solver, sim, gear["id"], "mark", ("frame", f"axle-{i}"))
            np.testing.assert_allclose(turned, expected, atol=1e-9, err_msg=f"seed {seed}")
            if i + 1 < len(gears):
                nxt = gears[i + 1]["gear"]
                sign = 1.0 if nxt["internal"] else -1.0
                expected = expected * sign * gear["gear"]["teeth"] / nxt["teeth"]


def test_a_rack_moves_its_pitch_radius_per_radian() -> None:
    for seed in range(4):
        sample = generate(family("rack-and-pinion"), seed)
        solver, sim = sweep(sample)
        pinion = next(b for b in sample.built.document["bodies"] if b["id"] == "pinion")
        pitch = float(pinion["gear"]["module"]) * int(pinion["gear"]["teeth"]) / 2
        path = track(solver, sim, "rack", "pitch")
        moved = np.hypot(*(path - path[0]).T)
        np.testing.assert_allclose(moved, pitch * np.abs(sim.drive - sim.drive[0]), atol=1e-9)


def test_belts_turn_pulleys_by_their_radius_ratio() -> None:
    for seed in range(4):
        sample = generate(family("belt-drive"), seed)
        solver, sim = sweep(sample)
        radii = {
            b["id"]: b["pulley"]["radius"]
            for b in sample.built.document["bodies"]
            if b["kind"] == "pulley"
        }
        belts = [j for j in sample.built.document["joints"] if j["kind"] == "belt"]
        for belt in belts:
            i = belt["bodyB"].split("-")[1]
            turned = turning(solver, sim, belt["bodyB"], "mark", ("frame", f"axle-{i}"))
            sign = -1.0 if belt["crossed"] else 1.0
            ratio = radii["pulley-0"] / radii[belt["bodyB"]]
            np.testing.assert_allclose(turned, sign * ratio * (sim.drive - sim.drive[0]), atol=1e-9)


def test_the_geneva_wheel_follows_the_closed_form_index_motion() -> None:
    for seed in range(4):
        sample = generate(family("geneva-drive"), seed)
        solver, sim = sweep(sample)
        n = int(sample.params["slots"])
        center = sample.params["scale"]
        crank = center * math.sin(math.pi / n)
        # With the pin at driver angle θ from the line of centers, the slot (and so the wheel)
        # points along the pin from the wheel's center.
        theta = sim.drive
        slot = np.arctan2(crank * np.sin(theta), crank * np.cos(theta) - center)
        expected = np.unwrap(slot) - np.unwrap(slot)[0]
        turned = turning(solver, sim, "wheel", "rim", ("frame", "g"))
        np.testing.assert_allclose(turned, expected, atol=1e-9)
        # Over the whole engagement the wheel would index one slot pitch.
        assert abs(turned[-1]) < math.tau / n


def cam_frame(
    solver: Solver, sim: Simulation, k: int, points: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    """World points in the cam's frame at sample `k` (the cam turns by the driver value)."""
    del solver
    c, s = math.cos(-sim.drive[k]), math.sin(-sim.drive[k])
    return points @ np.array([[c, s], [-s, c]])


def drawn_profile(sample: Sample) -> CamProfile:
    cam = next(b for b in sample.built.document["bodies"] if b["kind"] == "cam")["cam"]
    return CamProfile(cam["baseRadius"], tuple(cam["fourier"]["a"]), tuple(cam["fourier"]["b"]))


def test_knife_and_roller_followers_stay_on_the_profile() -> None:
    for kind, clearance in (("knife", 0.0), ("roller", 1.0)):
        for seed in range(3):
            sample = generate(family(f"cam-follower-{kind}"), seed)
            solver, sim = sweep(sample)
            profile = drawn_profile(sample)
            roller = sample.params["roller"] * sample.params["base"] * clearance
            dense = np.array([profile.point(float(p)) for p in np.linspace(0, math.tau, 20000)])
            # The nearest sampled profile point is within half a sample spacing of the true one.
            spacing = float(np.linalg.norm(np.diff(dense, axis=0), axis=1).max())
            contact = track(solver, sim, "follower", "contact")
            for k in range(0, len(sim.drive), 9):
                local: npt.NDArray[np.float64] = cam_frame(solver, sim, k, contact[k : k + 1])[0]
                distances: npt.NDArray[np.float64] = np.linalg.norm(dense - local, axis=1)
                gap = float(distances.min())
                assert abs(gap - roller) < spacing, (kind, seed, k, gap, roller)


def test_a_flat_face_rests_on_the_profile() -> None:
    for seed in range(3):
        sample = generate(family("cam-follower-flat"), seed)
        solver, sim = sweep(sample)
        profile = drawn_profile(sample)
        face = track(solver, sim, "follower", "contact")[:, 1]
        for k in range(0, len(sim.drive), 9):
            phis = np.linspace(0, math.tau, 20000)
            # The profile's highest point once the cam has turned by the driver value.
            heights = [profile.radius(float(p))[0] * math.sin(p + sim.drive[k]) for p in phis]
            assert abs(max(heights) - face[k]) < 1e-7


def test_the_needle_bar_runs_straight_and_the_take_up_eye_loops() -> None:
    for seed in range(3):
        sample = generate(family("sewing-machine"), seed)
        solver, sim = sweep(sample)
        needle = track(solver, sim, "needle-bar", "needle")
        centered = needle - needle.mean(axis=0)
        assert np.linalg.svd(centered, compute_uv=False)[-1] < 1e-9
        crank = sample.params["crank"] * sample.params["scale"]
        assert np.hypot(*np.ptp(needle, axis=0)) > 1.9 * crank
        eye = track(solver, sim, "take-up", "eye")
        np.testing.assert_allclose(eye[0], eye[-1], atol=1e-9)
        assert np.ptp(eye, axis=0).min() > 0.2 * crank
