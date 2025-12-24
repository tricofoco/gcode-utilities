"""
surfacing_gcode_v3.py

Generate simple surfacing (facing) toolpaths as G-code in **millimeters** (G21),
with automatic unit conversion from inches if requested.

Pattern: serpentine (zig-zag) along X with smooth 180° arc U-turns at each end,
stepping over in Y by the requested stepover.

Assumptions:
- XY origin at the lower-left corner of the rectangular face:
    X in [0, length], Y in [0, width]
- Z=0 is the top surface; cutting depths are negative.
- No tool diameter compensation; choose stepover/tool size accordingly.

Spindle:
- Emits M3 S<rpm> after moving to safe Z at the start.
- Emits M5 before M30 at the end.
- Set spindle_speed_rpm <= 0 to omit spindle commands.

Safety Z:
- Uses a single safe Z: `retract_z_mm` (also acts as "clearance").
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isclose
from typing import List, Literal

GeomUnit = Literal["inch", "in", "mm"]
RateUnit = Literal["in/min", "inch/min", "mm/min"]


@dataclass(frozen=True)
class SurfacingParams:
    width: float
    length: float
    final_depth: float
    max_stepdown: float
    stepover: float
    unit: GeomUnit = "inch"

    feed_rate: float = 80.0
    plunge_rate: float = 15.0
    rate_unit: RateUnit = "in/min"  # applies to BOTH feed and plunge

    spindle_speed_rpm: float = 12000.0  # set <=0 to skip spindle commands

    retract_z_mm: float = 5.0  # single safe Z height (mm)

    program_name: str = "surfacing"
    work_offset: str = "G54"


def _geom_to_mm(v: float, unit: GeomUnit) -> float:
    if unit == "mm":
        return float(v)
    if unit in ("inch", "in"):
        return float(v) * 25.4
    raise ValueError(f"Unsupported geometry unit: {unit}")


def _rate_to_mm_min(v: float, unit: RateUnit) -> float:
    if unit == "mm/min":
        return float(v)
    if unit in ("in/min", "inch/min"):
        return float(v) * 25.4
    raise ValueError(f"Unsupported rate unit: {unit}")


def _depth_levels(final_depth_mm: float, max_stepdown_mm: float) -> List[float]:
    """Return a list of negative Z depths ending exactly at -final_depth_mm."""
    if final_depth_mm <= 0:
        raise ValueError("final_depth must be > 0 (a positive number).")
    if max_stepdown_mm <= 0:
        raise ValueError("max_stepdown must be > 0 (a positive number).")

    target = -final_depth_mm
    step = max_stepdown_mm

    depths: List[float] = []
    z = 0.0
    while z > target:
        next_z = z - step
        if next_z < target:
            next_z = target
        depths.append(next_z)
        z = next_z
        if isclose(z, target, rel_tol=0.0, abs_tol=1e-9):
            break
    return depths


def generate_surfacing_gcode(
    width: float,
    length: float,
    final_depth: float,
    max_stepdown: float,
    stepover: float,
    unit: GeomUnit,
    feed_rate: float,
    plunge_rate: float,
    rate_unit: RateUnit,
    spindle_speed_rpm: float,
    retract_z_mm: float,
    *,
    program_name: str = "surfacing",
    work_offset: str = "G54",
) -> str:
    """
    Create a surfacing program as a single G-code string.

    - Geometry is converted to mm if `unit` is inches.
    - Feed/plunge rates are converted to mm/min using `rate_unit`.
    - Output uses:
        G90 (absolute), G21 (mm), G17 (XY plane)
    """
    # Convert geometry -> mm
    width_mm = _geom_to_mm(width, unit)
    length_mm = _geom_to_mm(length, unit)
    final_depth_mm = _geom_to_mm(final_depth, unit)
    max_stepdown_mm = _geom_to_mm(max_stepdown, unit)
    stepover_mm = _geom_to_mm(stepover, unit)

    if width_mm <= 0 or length_mm <= 0:
        raise ValueError("width and length must be > 0.")
    if stepover_mm <= 0:
        raise ValueError("stepover must be > 0.")
    if retract_z_mm <= 0:
        raise ValueError("retract_z_mm must be > 0 (mm).")

    # Convert rates -> mm/min (one unit for both)
    feed_mm_min = _rate_to_mm_min(feed_rate, rate_unit)
    plunge_mm_min = _rate_to_mm_min(plunge_rate, rate_unit)
    if feed_mm_min <= 0 or plunge_mm_min <= 0:
        raise ValueError("feed_rate and plunge_rate must be > 0.")

    depths = _depth_levels(final_depth_mm, max_stepdown_mm)

    # Pass planning in Y (include final edge)
    n_passes = int(ceil(width_mm / stepover_mm)) + 1
    ys = [min(i * stepover_mm, width_mm) for i in range(n_passes)]

    out: List[str] = []
    out.append(f"({program_name})")
    out.append("G90")
    out.append("G21")
    out.append("G17")
    out.append(work_offset)
    out.append("G64")
    out.append("")

    # Initial safe move
    out.append(f"G0 Z{retract_z_mm:.3f}")

    # Spindle on after reaching safe height
    if spindle_speed_rpm and spindle_speed_rpm > 0:
        out.append(f"M3 S{float(spindle_speed_rpm):.0f}")
    out.append("")

    for depth in depths:
        out.append(f"(Depth {depth:.3f} mm)")
        out.append("G0 X0.000 Y0.000")
        out.append(f"G0 Z{retract_z_mm:.3f}")
        out.append(f"G1 Z{depth:.3f} F{plunge_mm_min:.1f}")

        direction = +1  # +1 = X increasing, -1 = X decreasing

        for i, y in enumerate(ys):
            # Cut the pass
            if direction == +1:
                out.append(f"G1 X{length_mm:.3f} F{feed_mm_min:.1f}")
            else:
                out.append(f"G1 X0.000 F{feed_mm_min:.1f}")

            # If not last pass, U-turn to next Y with a 180° arc at the current X
            if i < len(ys) - 1:
                y_next = ys[i + 1]
                dy = y_next - y
                if dy <= 1e-9:
                    break

                # If the last increment is clamped (dy < stepover), adapt radius.
                r_local = dy / 2.0

                if direction == +1:
                    out.append(f"G3 X{length_mm:.3f} Y{y_next:.3f} I0.000 J{r_local:.3f}")
                else:
                    out.append(f"G2 X0.000 Y{y_next:.3f} I0.000 J{r_local:.3f}")

                direction *= -1

        out.append(f"G0 Z{retract_z_mm:.3f}")
        out.append("")

    out.append(f"G0 Z{retract_z_mm:.3f}")

    # Spindle off at the end
    if spindle_speed_rpm and spindle_speed_rpm > 0:
        out.append("M5")

    out.append("M30")
    out.append("")
    return "\n".join(out)


def generate_from_params(params: SurfacingParams) -> str:
    return generate_surfacing_gcode(
        width=params.width,
        length=params.length,
        final_depth=params.final_depth,
        max_stepdown=params.max_stepdown,
        stepover=params.stepover,
        unit=params.unit,
        feed_rate=params.feed_rate,
        plunge_rate=params.plunge_rate,
        rate_unit=params.rate_unit,
        spindle_speed_rpm=params.spindle_speed_rpm,
        retract_z_mm=params.retract_z_mm,
        program_name=params.program_name,
        work_offset=params.work_offset,
    )


if __name__ == "__main__":
    gcode = generate_surfacing_gcode(
        width=10,
        length=10,
        final_depth=0.1,
        max_stepdown=0.05,
        stepover=2,
        unit="inch",
        feed_rate=80,
        plunge_rate=15,
        rate_unit="in/min",
        spindle_speed_rpm=12000,
        retract_z_mm=5.0,
        program_name="example_10x10in_surface",
    )
    with open("surface_10x10.nc", "w") as f:
        f.write(gcode)
    print("Wrote surface_10x10.nc")
