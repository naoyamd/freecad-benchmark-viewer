"""RLG-003 normal and emergency retraction sizing.

This is a boundary-driven hydraulic calculation, not a dynamic flight model.
It keeps the required supply, accumulator, actuator geometry, load moment and
projected-area inputs explicit.  Missing load-boundary inputs remain incomplete
instead of being replaced by an optimistic hidden assumption.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
MECHANISM_DIR = ROOT / "cad" / "rlg003"
if str(MECHANISM_DIR) not in sys.path:
    sys.path.insert(0, str(MECHANISM_DIR))
from mechanism_math import main_actuator_state  # noqa: E402


G = 9.80665
RHO_AIR = 1.225
CD_A = 1.2


def _number(source: Mapping[str, Any], names: Sequence[str], default: float | None) -> float | None:
    for name in names:
        if name in source:
            try:
                return float(source[name])
            except (TypeError, ValueError):
                pass
    return default


def _read_json(path: str | Path) -> Mapping[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("retraction input JSON must contain an object")
    return value


def motion_rows(source: str | Path | Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Load parent-produced per-theta mass/CG/projected-area snapshots."""

    value: Any = None
    if isinstance(source, Mapping):
        value = source
    elif source is not None:
        value = _read_json(source)
    else:
        candidates = (
            ROOT / "analysis" / "motion_boundaries.json",
            ROOT / "work" / "motion_boundaries.json",
            ROOT / "outputs" / "RLG-003_Astra_Luna_r02" / "motion_boundaries.json",
            ROOT / "outputs" / "RLG-003_Astra_Luna_r02" / "deliverables" / "motion_boundaries.json",
        )
        for candidate in candidates:
            if candidate.exists():
                value = _read_json(candidate)
                break
        if value is None:
            try:
                import motion_boundaries  # type: ignore

                producer = getattr(motion_boundaries, "motion_rows", None)
                if callable(producer):
                    value = {"rows": producer()}
            except Exception:
                value = None
    if not isinstance(value, Mapping):
        return []
    rows = value.get("rows", value.get("theta_snapshots", value.get("snapshots", [])))
    return [dict(row) for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []


@dataclass(frozen=True)
class RetractionBoundary:
    mass_kg: float = 9200.0
    mass_source: str = "provisional current CAD mass boundary; final BOM pending"
    cg_radius_m: float | None = None
    projected_area_m2: float | None = None
    base_load_moment_nm: float | None = None
    snapshots: tuple[Mapping[str, Any], ...] = ()
    main_actuator_count: int = 2
    main_bore_m: float = 0.160
    main_rod_m: float = 0.090
    main_geometric_stroke_m: float = 0.8772621907630446
    last10deg_oil_l: float = 1.4
    emergency_flow_lpm: float = 120.0
    normal_supply_mpa: float = 20.7
    normal_guarantee_mpa: float = 17.0
    return_mpa: float = 0.3
    max_flow_lpm: float = 120.0
    air_density_kg_m3: float = RHO_AIR
    air_cd_area: float = CD_A
    normal_motion_s: float = 20.0
    door_open_s: float = 3.0
    door_close_s: float = 3.0
    emergency_limit_s: float = 60.0
    emergency_theta_start_deg: float = 20.0
    joint_friction_n: float = 2000.0
    angular_accel_rad_s2: float = 0.0

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any] | None = None) -> "RetractionBoundary":
        source = source or {}
        nested = source.get("retraction", source.get("analysis", source))
        if not isinstance(nested, Mapping):
            nested = {}
        mass = _number(nested, ("mass_kg", "cad_mass_kg"), None)
        if mass is None and isinstance(nested.get("cad_mass"), Mapping):
            mass = _number(nested["cad_mass"], ("mass_kg",), None)
        raw_snapshots = nested.get("theta_snapshots", nested.get("snapshots", ()))
        snapshots = tuple(dict(row) for row in raw_snapshots if isinstance(row, Mapping)) if isinstance(raw_snapshots, list) else ()
        if not snapshots:
            snapshots = tuple(motion_rows())
        mass_source = "explicit JSON boundary" if mass is not None else cls.mass_source
        if mass is None and snapshots:
            mass = _number(snapshots[0], ("mass_kg",), None)
            if mass is not None:
                mass_source = "current CAD dry-mass snapshots; hydraulic fluid excluded"
        bore = _number(nested, ("main_bore_m",), cls.main_bore_m) or cls.main_bore_m
        rod = _number(nested, ("main_rod_m",), cls.main_rod_m) or cls.main_rod_m
        assist_start = _number(nested, ("emergency_theta_start_deg",), cls.emergency_theta_start_deg)
        default_last10 = 2.0 * math.pi * bore**2 / 4.0 * (main_actuator_state(0.0, 0.0).length - main_actuator_state(assist_start, 0.0).length)
        return cls(
            mass_kg=mass if mass is not None else cls.mass_kg,
            mass_source=mass_source,
            cg_radius_m=_number(nested, ("cg_radius_m", "load_radius_m"), None),
            projected_area_m2=_number(nested, ("projected_area_m2", "main_projected_area_m2"), None),
            base_load_moment_nm=_number(nested, ("base_load_moment_nm", "load_moment_nm"), None),
            snapshots=snapshots,
            main_actuator_count=int(_number(nested, ("main_actuator_count",), cls.main_actuator_count) or cls.main_actuator_count),
            main_bore_m=bore,
            main_rod_m=rod,
            main_geometric_stroke_m=_number(nested, ("main_geometric_stroke_m", "actuator_stroke_m"), cls.main_geometric_stroke_m) or cls.main_geometric_stroke_m,
            last10deg_oil_l=_number(nested, ("last10deg_oil_l", "emergency_oil_l"), default_last10) or default_last10,
            emergency_flow_lpm=_number(nested, ("emergency_flow_lpm",), cls.emergency_flow_lpm) or cls.emergency_flow_lpm,
            normal_supply_mpa=_number(nested, ("normal_supply_mpa",), cls.normal_supply_mpa) or cls.normal_supply_mpa,
            normal_guarantee_mpa=_number(nested, ("normal_guarantee_mpa",), cls.normal_guarantee_mpa) or cls.normal_guarantee_mpa,
            return_mpa=_number(nested, ("return_mpa",), cls.return_mpa) or cls.return_mpa,
            max_flow_lpm=_number(nested, ("max_flow_lpm",), cls.max_flow_lpm) or cls.max_flow_lpm,
            air_density_kg_m3=_number(nested, ("air_density_kg_m3",), cls.air_density_kg_m3) or cls.air_density_kg_m3,
            air_cd_area=_number(nested, ("air_cd_area",), cls.air_cd_area) or cls.air_cd_area,
            normal_motion_s=_number(nested, ("normal_motion_s",), cls.normal_motion_s) or cls.normal_motion_s,
            door_open_s=_number(nested, ("door_open_s",), cls.door_open_s) or cls.door_open_s,
            door_close_s=_number(nested, ("door_close_s",), cls.door_close_s) or cls.door_close_s,
            emergency_limit_s=_number(nested, ("emergency_limit_s",), cls.emergency_limit_s) or cls.emergency_limit_s,
            emergency_theta_start_deg=_number(nested, ("emergency_theta_start_deg",), cls.emergency_theta_start_deg) or cls.emergency_theta_start_deg,
            joint_friction_n=_number(nested, ("joint_friction_n",), cls.joint_friction_n) or cls.joint_friction_n,
            angular_accel_rad_s2=_number(nested, ("angular_accel_rad_s2",), cls.angular_accel_rad_s2) or cls.angular_accel_rad_s2,
        )


@dataclass(frozen=True)
class AccumulatorConfig:
    shell_volume_l: float = 12.0
    precharge_abs_mpa: float = 10.0
    # The accumulator sizing boundary uses the stated 10/20.7/17 MPa values
    # on one common design-pressure basis; the hydraulic supply is separately
    # labelled as gauge pressure in RetractionBoundary.
    charge_abs_mpa: float = 20.801325
    polytropic_n: float = 1.3
    minimum_supply_mpa: float = 17.0
    required_oil_l: float = 4.00909407264309


def annular_area_m2(boundary: RetractionBoundary) -> float:
    return math.pi * (boundary.main_bore_m**2 - boundary.main_rod_m**2) / 4.0


def accumulator_pressure_mpa(oil_delivered_l: float, config: AccumulatorConfig = AccumulatorConfig()) -> float:
    """Return accumulator absolute pressure after a specified oil delivery."""

    if oil_delivered_l < 0:
        raise ValueError("oil_delivered_l must be non-negative")
    gas_at_charge_l = config.shell_volume_l * (config.precharge_abs_mpa / config.charge_abs_mpa) ** (1.0 / config.polytropic_n)
    gas_after_l = gas_at_charge_l + oil_delivered_l
    return config.charge_abs_mpa * (gas_at_charge_l / gas_after_l) ** config.polytropic_n


def accumulator_result(config: AccumulatorConfig = AccumulatorConfig()) -> dict[str, Any]:
    gas_at_charge_l = config.shell_volume_l * (config.precharge_abs_mpa / config.charge_abs_mpa) ** (1.0 / config.polytropic_n)
    full_oil_l = config.shell_volume_l - gas_at_charge_l
    gas_at_min_l = gas_at_charge_l * (config.charge_abs_mpa / config.minimum_supply_mpa) ** (1.0 / config.polytropic_n)
    oil_to_min_l = max(0.0, gas_at_min_l - gas_at_charge_l)
    final_abs_mpa = accumulator_pressure_mpa(config.required_oil_l, config)
    final_gauge_mpa = final_abs_mpa - 0.101325
    return {
        "shell_volume_l": config.shell_volume_l,
        "precharge_abs_mpa": config.precharge_abs_mpa,
        "charge_abs_mpa": config.charge_abs_mpa,
        "polytropic_n": config.polytropic_n,
        "gas_volume_at_charge_l": gas_at_charge_l,
        "maximum_oil_displacement_l": full_oil_l,
        "oil_available_while_above_17_mpa_l": oil_to_min_l,
        "required_oil_l": config.required_oil_l,
        "pressure_after_required_abs_mpa": final_abs_mpa,
        "pressure_after_required_gauge_mpa": final_gauge_mpa,
        "pressure_floor_mpa": config.minimum_supply_mpa,
        "pressure_floor_pass": final_gauge_mpa >= config.minimum_supply_mpa,
        "pressure_path": [
            {"oil_delivered_l": value, "pressure_mpa": accumulator_pressure_mpa(value, config)}
            for value in (0.0, config.required_oil_l * 0.25, config.required_oil_l * 0.5, config.required_oil_l * 0.75, config.required_oil_l)
        ],
    }


def main_leverage_path(start_deg: float = 0.0, end_deg: float = 90.0, step_deg: float = 1.0) -> list[dict[str, float]]:
    rows = []
    theta = start_deg
    while theta <= end_deg + 1.0e-9:
        state = main_actuator_state(theta, 0.0)
        rows.append({"theta_deg": theta, "length_m": state.length / 1000.0, "lever_arm_m": state.lever_arm_mm / 1000.0})
        theta += step_deg
    return rows


REQUIRED_SNAPSHOT_FIELDS = (
    "theta_deg",
    "mass_kg",
    "cg_y_m",
    "cg_z_m",
    "Ix_kg_m2",
    "area_yz_m2",
    "cp_y_m",
    "cp_z_m",
)
DERIVATIVE_SNAPSHOT_FIELDS = ("dMy_dtheta_kgm", "dMz_dtheta_kgm")


def required_snapshot_fields() -> tuple[str, ...]:
    """Fields the parent CAD/mass integration must provide per theta row."""

    return REQUIRED_SNAPSHOT_FIELDS


def _snapshot_at(theta_deg: float, boundary: RetractionBoundary) -> Mapping[str, float] | None:
    rows = [row for row in boundary.snapshots if all(key in row for key in REQUIRED_SNAPSHOT_FIELDS)]
    if not rows:
        return None
    ordered = sorted(rows, key=lambda row: float(row["theta_deg"]))
    def values(row):
        result = {key: float(row[key]) for key in REQUIRED_SNAPSHOT_FIELDS}
        for optional in (*DERIVATIVE_SNAPSHOT_FIELDS, "angular_accel_rad_s2"):
            if optional in row:
                result[optional] = float(row[optional])
        return result
    if theta_deg <= float(ordered[0]["theta_deg"]):
        return values(ordered[0])
    if theta_deg >= float(ordered[-1]["theta_deg"]):
        return values(ordered[-1])
    for low, high in zip(ordered, ordered[1:]):
        lo = float(low["theta_deg"])
        hi = float(high["theta_deg"])
        if lo <= theta_deg <= hi:
            fraction = (theta_deg - lo) / max(hi - lo, 1.0e-12)
            result = {
                key: float(low[key]) + fraction * (float(high[key]) - float(low[key]))
                for key in REQUIRED_SNAPSHOT_FIELDS
            }
            for optional in (*DERIVATIVE_SNAPSHOT_FIELDS, "angular_accel_rad_s2"):
                if optional in low and optional in high:
                    result[optional] = float(low[optional]) + fraction * (float(high[optional]) - float(low[optional]))
            return result
    return None


def _force_moment_snapshot(snapshot: Mapping[str, float], speed_m_s: float, pitch_deg: float, roll_deg: float, boundary: RetractionBoundary) -> dict[str, float]:
    """Compute exact X-axis moments from gravity and specified lateral air load."""

    pitch = math.radians(pitch_deg)
    roll = math.radians(roll_deg)
    fz = -snapshot["mass_kg"] * G * math.cos(roll) * math.cos(pitch)
    fy = snapshot["mass_kg"] * G * math.sin(roll) * math.cos(pitch)
    legacy_mx = snapshot["cg_y_m"] * fz - snapshot["cg_z_m"] * fy
    if all(key in snapshot for key in DERIVATIVE_SNAPSHOT_FIELDS):
        gravity_mx = G * (math.sin(roll) * math.cos(pitch) * snapshot["dMy_dtheta_kgm"] - math.cos(roll) * math.cos(pitch) * snapshot["dMz_dtheta_kgm"])
        gravity_moment_source = "per-theta first-moment derivatives"
    else:
        # Legacy rigid-rotation identity, retained only when the parent has
        # not supplied derivatives.  This is reported explicitly in output.
        dmy = snapshot["mass_kg"] * snapshot["cg_z_m"]
        dmz = -snapshot["mass_kg"] * snapshot["cg_y_m"]
        gravity_mx = G * (math.sin(roll) * math.cos(pitch) * dmy - math.cos(roll) * math.cos(pitch) * dmz)
        gravity_moment_source = "legacy rigid-rotation identity"
    area = snapshot["area_yz_m2"]
    air_force = 0.5 * boundary.air_density_kg_m3 * speed_m_s**2 * boundary.air_cd_area * area
    lateral = 0.3 * air_force
    air_mx = abs(snapshot["cp_z_m"]) * lateral
    inertia_mx = snapshot.get("angular_accel_rad_s2", boundary.angular_accel_rad_s2) * snapshot["Ix_kg_m2"]
    return {
        "gravity_fy_n": fy,
        "gravity_fz_n": fz,
        "gravity_mx_nm": gravity_mx,
        "legacy_point_mx_nm": legacy_mx,
        "gravity_moment_source": gravity_moment_source,
        "air_drag_force_n": air_force,
        "air_lateral_force_abs_n": lateral,
        "air_mx_nm_worst_sign": air_mx,
        "inertia_mx_nm": inertia_mx,
        "total_mx_nm": gravity_mx + air_mx + inertia_mx,
    }


def normal_retraction_calculation(boundary: RetractionBoundary) -> dict[str, Any]:
    area = annular_area_m2(boundary)
    bore_area = math.pi * boundary.main_bore_m**2 / 4.0
    length_down_m = main_actuator_state(0.0, 0.0).length / 1000.0
    length_stowed_m = main_actuator_state(90.0, 0.0).length / 1000.0
    geometric_stroke_m = length_down_m - length_stowed_m
    volume_l = area * geometric_stroke_m * boundary.main_actuator_count * 1000.0
    flow_lpm = volume_l / boundary.normal_motion_s * 60.0
    pressure_path = [
        {
            "pressure_gauge_mpa": pressure,
            "force_pair_n": 2.0 * (pressure * 1.0e6 * area - boundary.return_mpa * 1.0e6 * bore_area),
            "force_per_actuator_n": pressure * 1.0e6 * area - boundary.return_mpa * 1.0e6 * bore_area,
        }
        for pressure in (boundary.normal_guarantee_mpa, boundary.normal_supply_mpa)
    ]
    leverage = main_leverage_path()
    torque_path = [
        {
            "theta_deg": row["theta_deg"],
            "lever_arm_m": row["lever_arm_m"],
            "force_at_17_mpa_pair_n": pressure_path[0]["force_pair_n"],
            "torque_at_17_mpa_nm": pressure_path[0]["force_pair_n"] * row["lever_arm_m"],
            "force_at_20_7_mpa_pair_n": pressure_path[1]["force_pair_n"],
            "torque_at_20_7_mpa_nm": pressure_path[1]["force_pair_n"] * row["lever_arm_m"],
        }
        for row in leverage
    ]
    timeline = [
        {"step": "door_open", "start_s": 0.0, "end_s": boundary.door_open_s, "duration_s": boundary.door_open_s, "flow_boundary_lpm": None},
        {"step": "main_retraction", "start_s": boundary.door_open_s, "end_s": boundary.door_open_s + boundary.normal_motion_s, "duration_s": boundary.normal_motion_s, "flow_boundary_lpm": flow_lpm},
        {"step": "door_close", "start_s": boundary.door_open_s + boundary.normal_motion_s, "end_s": boundary.door_open_s + boundary.normal_motion_s + boundary.door_close_s, "duration_s": boundary.door_close_s, "flow_boundary_lpm": None},
    ]
    total_time_s = boundary.normal_motion_s + boundary.door_open_s + boundary.door_close_s
    normal_load_rows = []
    normal_pair_force_n = pressure_path[0]["force_pair_n"]
    for speed_m_s in (0.0, 80.0, 110.0):
        for theta in range(0, 91, 1):
            snapshot = _snapshot_at(float(theta), boundary)
            if snapshot is None:
                continue
            moment = _force_moment_snapshot(snapshot, speed_m_s, 0.0, 0.0, boundary)
            lever = main_actuator_state(float(theta), 0.0).lever_arm_mm / 1000.0
            required_torque = abs(moment["gravity_mx_nm"]) + moment["air_mx_nm_worst_sign"] + abs(moment["inertia_mx_nm"]) + boundary.joint_friction_n * lever
            available_torque = normal_pair_force_n * lever
            normal_load_rows.append({"speed_m_s": speed_m_s, "theta_deg": theta, **moment, "required_torque_nm": required_torque, "available_torque_nm": available_torque, "torque_margin_nm": available_torque - required_torque})
    normal_load_complete = len(normal_load_rows) == 273
    return {
        "hydraulic_path": ["20.7 MPa source", "17.0 MPa guarantee boundary", "two main actuator annular chambers", "0.3 MPa return"],
        "annular_area_m2": area,
        "main_geometric_stroke_m": geometric_stroke_m,
        "main_actuator_count": boundary.main_actuator_count,
        "main_oil_volume_l": volume_l,
        "required_main_flow_lpm": flow_lpm,
        "max_flow_lpm": boundary.max_flow_lpm,
        "flow_within_120_lpm": flow_lpm <= boundary.max_flow_lpm,
        "pressure_path": pressure_path,
        "torque_path": torque_path,
        "normal_load_path": normal_load_rows,
        "normal_load_boundary_complete": normal_load_complete,
        "normal_load_torque_pass": normal_load_complete and all(row["torque_margin_nm"] >= 0.0 for row in normal_load_rows),
        "timeline": timeline,
        "total_time_s": total_time_s,
        "total_time_within_26_s": total_time_s <= 26.0,
        "door_flow_boundary_complete": True,
        "note": "Doors use the specification's ideal 3 s motion; separate door hydraulic hardware sizing is outside the task scope.",
    }


def emergency_retraction_calculation(boundary: RetractionBoundary) -> dict[str, Any]:
    bore_area = math.pi * boundary.main_bore_m**2 / 4.0
    length_90_m = main_actuator_state(90.0, 0.0).length / 1000.0
    length_10_m = main_actuator_state(boundary.emergency_theta_start_deg, 0.0).length / 1000.0
    length_0_m = main_actuator_state(0.0, 0.0).length / 1000.0
    gravity_descent_volume_l = 2.0 * bore_area * (length_10_m - length_90_m) * 1000.0
    last10_geometry_l = 2.0 * bore_area * (length_0_m - length_10_m) * 1000.0
    accumulator = accumulator_result(AccumulatorConfig(required_oil_l=boundary.last10deg_oil_l))
    last10_leverage = main_leverage_path(0.0, boundary.emergency_theta_start_deg, 1.0)
    min_last10_lever_m = min(row["lever_arm_m"] for row in last10_leverage)
    bypass_flow = boundary.emergency_flow_lpm
    gravity_time_s = None if bypass_flow <= 0 else gravity_descent_volume_l / bypass_flow * 60.0
    last10_time_s = None if bypass_flow <= 0 else boundary.last10deg_oil_l / bypass_flow * 60.0
    total_time_s = None if gravity_time_s is None or last10_time_s is None else boundary.door_open_s + gravity_time_s + last10_time_s

    cases = []
    for speed_m_s in (0.0, 80.0, 110.0):
        for pitch_deg in (-5.0, 0.0, 5.0):
            for roll_deg in (-5.0, 0.0, 5.0):
                descent_rows = []
                assist_rows = []
                for theta in range(int(boundary.emergency_theta_start_deg), 91, 5):
                    snapshot = _snapshot_at(float(theta), boundary)
                    if snapshot is not None:
                        moment = _force_moment_snapshot(snapshot, speed_m_s, pitch_deg, roll_deg, boundary)
                        lever = main_actuator_state(float(theta), 0.0).lever_arm_mm / 1000.0
                        friction_torque = boundary.joint_friction_n * lever
                        drive_budget = -moment["gravity_mx_nm"] - moment["air_mx_nm_worst_sign"] - friction_torque - abs(moment["inertia_mx_nm"])
                        descent_rows.append({"theta_deg": theta, **moment, "friction_torque_nm": friction_torque, "positive_gravity_drive_budget_nm": drive_budget})
                for theta in range(0, int(boundary.emergency_theta_start_deg) + 1, 1):
                    snapshot = _snapshot_at(float(theta), boundary)
                    if snapshot is not None:
                        moment = _force_moment_snapshot(snapshot, speed_m_s, pitch_deg, roll_deg, boundary)
                        lever = main_actuator_state(float(theta), 0.0).lever_arm_mm / 1000.0
                        friction_torque = boundary.joint_friction_n * lever
                        assist_rows.append({"theta_deg": theta, **moment, "friction_torque_nm": friction_torque, "required_assist_torque_nm": max(0.0, moment["total_mx_nm"]) + friction_torque, "lever_arm_m": lever})
                boundary_complete = len(descent_rows) == len(range(int(boundary.emergency_theta_start_deg), 91, 5)) and len(assist_rows) == int(boundary.emergency_theta_start_deg) + 1
                gravity_budget = min((row["positive_gravity_drive_budget_nm"] for row in descent_rows), default=None)
                required_assist_torque = max((row["required_assist_torque_nm"] for row in assist_rows), default=None)
                acc_pressure_abs_mpa = accumulator["pressure_after_required_abs_mpa"]
                emergency_force_pair_n = 2.0 * ((acc_pressure_abs_mpa - 0.101325) * 1.0e6 * bore_area - boundary.return_mpa * 1.0e6 * annular_area_m2(boundary))
                available_assist_torque = emergency_force_pair_n * min_last10_lever_m
                cases.append({
                    "speed_m_s": speed_m_s,
                    "pitch_deg": pitch_deg,
                    "roll_deg": roll_deg,
                    "gravity_descent_positive_budget_min_nm": gravity_budget,
                    "last10_required_assist_torque_max_nm": required_assist_torque,
                    "emergency_force_pair_n": emergency_force_pair_n,
                    "emergency_available_assist_torque_nm": available_assist_torque,
                    "gravity_descent_pass": boundary_complete and (gravity_budget is not None and gravity_budget > 0.0),
                    "last10_torque_pass": boundary_complete and (required_assist_torque is not None and available_assist_torque >= required_assist_torque),
                    "boundary_complete": boundary_complete,
                    "descent_path": descent_rows,
                    "assist_path": assist_rows,
                })
    complete = all(case["boundary_complete"] for case in cases)
    torque_pass = complete and all(case["gravity_descent_pass"] and case["last10_torque_pass"] for case in cases)
    time_pass = total_time_s is not None and total_time_s <= boundary.emergency_limit_s
    return {
        "hydraulic_path": ["normal source=0", "manual uplock release", "normally closed isolation valve", "gravity descent through viscous bypass at controlled 120 L/min", "12 L accumulator assist", "cam/bypass opens for Theta=20..0 deg", "main actuator full-bore extension chamber", "0.3 MPa return/bypass"],
        "valve_open_start_theta_deg": boundary.emergency_theta_start_deg,
        "manual_uplock_release_required": True,
        "theta_direction": "90 deg stowed -> 10 deg gravity descent -> 0 deg accumulator assist",
        "gravity_descent_volume_l": gravity_descent_volume_l,
        "last10deg_geometry_oil_l": last10_geometry_l,
        "last10deg_oil_l": boundary.last10deg_oil_l,
        "emergency_flow_lpm": boundary.emergency_flow_lpm,
        "gravity_descent_time_s": gravity_time_s,
        "last10_assist_time_s": last10_time_s,
        "door_open_time_s": boundary.door_open_s,
        "calculated_time_s": total_time_s,
        "within_60_s": time_pass,
        "last10deg_min_lever_m": min_last10_lever_m,
        "accumulator": accumulator,
        "cases": cases,
        "load_boundary_complete": complete,
        "torque_budget_pass": torque_pass,
        "status": "PASS" if complete and torque_pass and time_pass else ("INCOMPLETE" if not complete else "FAIL"),
        "note": "Gravity/air moments use per-theta CAD mass/CG/projected-area snapshots; no full air drag moment or hidden gravity radius is substituted.",
    }


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def run_analysis(output_dir: str | Path, input_path: str | Path | None = None) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    raw = _read_json(input_path) if input_path else {}
    boundary = RetractionBoundary.from_mapping(raw)
    normal = normal_retraction_calculation(boundary)
    emergency = emergency_retraction_calculation(boundary)
    leverage = main_leverage_path()
    _write_csv(out / "retraction_normal_path.csv", normal["timeline"] + normal["pressure_path"])
    _write_csv(out / "retraction_normal_torque.csv", normal["torque_path"])
    _write_csv(out / "retraction_normal_load_path.csv", normal["normal_load_path"])
    _write_csv(out / "retraction_emergency_path.csv", emergency["cases"])
    _write_csv(out / "retraction_main_leverage.csv", leverage)
    (out / "retraction_accumulator.json").write_text(json.dumps(emergency["accumulator"], indent=2), encoding="utf-8")
    summary = {
        "boundary": asdict(boundary),
        "required_snapshot_fields": list(REQUIRED_SNAPSHOT_FIELDS),
        "normal": normal,
        "emergency": emergency,
        "status": "PASS" if normal["flow_within_120_lpm"] and normal["total_time_within_26_s"] and normal["normal_load_torque_pass"] and emergency["status"] == "PASS" else ("INCOMPLETE" if not normal["normal_load_boundary_complete"] or emergency["status"] == "INCOMPLETE" else "FAIL"),
        "limitations": [boundary.mass_source, "emergency projected area and CG/load moment are explicit JSON boundaries", "no valve transient, hose elasticity, or flight-control software model"],
    }
    (out / "retraction_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RLG-003 normal/emergency retraction boundary analysis")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--input")
    args = parser.parse_args(argv)
    summary = run_analysis(args.output_dir, args.input)
    print(json.dumps({"output_dir": str(Path(args.output_dir).resolve()), "status": summary["status"], "emergency_status": summary["emergency"]["status"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
