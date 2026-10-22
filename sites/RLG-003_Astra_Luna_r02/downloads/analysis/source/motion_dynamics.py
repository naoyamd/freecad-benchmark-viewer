"""Bounded normal and emergency main-gear motion dynamics.

The model is deliberately a force/flow/time-history screen.  It reuses the
parent retraction boundary snapshots and mechanism kinematics, records signed
loads, and keeps lock/stop and fluid-path assumptions visible instead of
turning missing geometry into a pass.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from bisect import bisect_right
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:
    from .retraction import (
        AccumulatorConfig,
        RetractionBoundary,
        _force_moment_snapshot,
        _snapshot_at,
        accumulator_pressure_mpa,
        main_actuator_state,
        motion_rows,
    )
except ImportError:  # pragma: no cover - direct script execution
    from retraction import (  # type: ignore
        AccumulatorConfig,
        RetractionBoundary,
        _force_moment_snapshot,
        _snapshot_at,
        accumulator_pressure_mpa,
        main_actuator_state,
        motion_rows,
    )


G = 9.80665
P_ATM_MPA = 0.101325
RHO_OIL = 870.0
CD_ORIFICE = 0.65
WHEEL_DAMPING_ORIFICE_M2 = 17.0e-6
AIR_SPEEDS_M_S = (0.0, 80.0, 110.0)
ATTITUDES_DEG = ((0.0, 0.0), (5.0, 0.0), (-5.0, 0.0), (0.0, 5.0), (0.0, -5.0))


@dataclass(frozen=True)
class MotionConfig:
    normal_motion_s: float = 18.8
    normal_ramp_s: float = 1.0
    normal_overhead_s: float = 1.0
    normal_dt_s: float = 0.002
    emergency_dt_s: float = 0.002
    record_interval_s: float = 0.05
    pin_mu_normal: tuple[float, float] = (0.05, 0.10)
    pin_mu_emergency: float = 0.10
    hose_force_n: float = 2_000.0
    flow_cap_m3_s: float = 0.002
    bypass_orifice_m2: float = WHEEL_DAMPING_ORIFICE_M2
    bypass_cd: float = CD_ORIFICE
    oil_density_kg_m3: float = RHO_OIL
    emergency_pressure_mpa: float = 0.3
    lock_overhead_limit_s: float = 1.2
    engineering_lock_allowance_s: float = 1.0
    emergency_max_s: float = 60.0


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def annular_area_m2(boundary: RetractionBoundary) -> float:
    return math.pi * (boundary.main_bore_m**2 - boundary.main_rod_m**2) / 4.0


def bore_area_m2(boundary: RetractionBoundary) -> float:
    return math.pi * boundary.main_bore_m**2 / 4.0


def actuator_length_derivatives(theta_deg: float) -> tuple[float, float, float]:
    """Return L, dL/dtheta and d2L/dtheta2 in SI units/radians.

    The fixed main-actuator points reduce to
    ``L² = 2.98e6 - 0.9e6 sin(theta) + 2.4e6 cos(theta)`` in mm².
    The derivative agrees with ``main_actuator_state(...).lever_arm_mm`` and
    avoids noisy finite differences in the time history.
    """

    theta = math.radians(theta_deg)
    sin_t, cos_t = math.sin(theta), math.cos(theta)
    length_sq = 2_980_000.0 - 900_000.0 * sin_t + 2_400_000.0 * cos_t
    length_mm = math.sqrt(max(length_sq, 1.0e-12))
    first_sq = -900_000.0 * cos_t - 2_400_000.0 * sin_t
    second_sq = 900_000.0 * sin_t - 2_400_000.0 * cos_t
    first_mm_rad = first_sq / (2.0 * length_mm)
    second_mm_rad2 = second_sq / (2.0 * length_mm) - first_sq**2 / (4.0 * length_mm**3)
    return length_mm / 1000.0, first_mm_rad / 1000.0, second_mm_rad2 / 1000.0


def inverse_actuator_theta(length_m: float) -> float:
    """Invert monotonic main actuator length over theta=0..90 degrees."""

    lo, hi = 0.0, 90.0
    l0 = actuator_length_derivatives(lo)[0]
    l90 = actuator_length_derivatives(hi)[0]
    if length_m >= l0:
        return lo
    if length_m <= l90:
        return hi
    theta = 90.0 * (l0 - length_m) / max(l0 - l90, 1.0e-12)
    for _ in range(12):
        value, derivative, _ = actuator_length_derivatives(theta)
        if value > length_m:
            lo = theta
        else:
            hi = theta
        if abs(derivative) < 1.0e-12:
            break
        trial = theta - (value - length_m) / derivative * 180.0 / math.pi
        if not lo < trial < hi:
            trial = 0.5 * (lo + hi)
        theta = trial
    return min(max(theta, 0.0), 90.0)


def trapezoid_profile(time_s: float, total_distance_m: float, total_time_s: float, ramp_s: float) -> tuple[float, float, float]:
    """Distance, speed and acceleration for a symmetric trapezoid."""

    ramp = min(ramp_s, total_time_s / 2.0)
    vmax = total_distance_m / max(total_time_s - ramp, 1.0e-12)
    accel = vmax / max(ramp, 1.0e-12)
    t = min(max(time_s, 0.0), total_time_s)
    if t <= ramp:
        return 0.5 * accel * t * t, accel * t, accel
    if t <= total_time_s - ramp:
        return 0.5 * accel * ramp * ramp + vmax * (t - ramp), vmax, 0.0
    tail = total_time_s - t
    return total_distance_m - 0.5 * accel * tail * tail, accel * tail, -accel


def pin_friction_torque_n_m(mu: float, mass_kg: float, pair_cylinder_force_n: float, *, stay_weight_force_n: float | None = None) -> float:
    """Bounded pin-friction estimate required by the motion boundary."""

    stay_weight = mass_kg * G if stay_weight_force_n is None else stay_weight_force_n
    return mu * (mass_kg * G * 0.12 + 2.0 * abs(pair_cylinder_force_n) * 0.06 + stay_weight * 4.0 * 0.06)


def _verified_inertia(boundary: RetractionBoundary) -> float:
    values = [float(row["Ix_kg_m2"]) for row in boundary.snapshots if "Ix_kg_m2" in row]
    return max(values) if values else 0.0


def _make_snapshot_lookup(boundary: RetractionBoundary):
    """Prepare the 19-row interpolation once for the emergency ODE hot loop."""

    required = ("theta_deg", "mass_kg", "cg_y_m", "cg_z_m", "Ix_kg_m2", "area_yz_m2", "cp_y_m", "cp_z_m", "dMy_dtheta_kgm", "dMz_dtheta_kgm")
    rows = [row for row in boundary.snapshots if all(key in row for key in required)]
    ordered = sorted(rows, key=lambda row: float(row["theta_deg"]))
    angles = [float(row["theta_deg"]) for row in ordered]

    def lookup(theta_deg: float) -> Mapping[str, float] | None:
        if not ordered:
            return None
        if theta_deg <= angles[0]:
            return {key: float(ordered[0][key]) for key in required}
        if theta_deg >= angles[-1]:
            return {key: float(ordered[-1][key]) for key in required}
        index = bisect_right(angles, theta_deg) - 1
        low, high = ordered[index], ordered[index + 1]
        fraction = (theta_deg - angles[index]) / max(angles[index + 1] - angles[index], 1.0e-12)
        return {key: float(low[key]) + fraction * (float(high[key]) - float(low[key])) for key in required}

    return lookup


def _sample_due(time_s: float, next_sample_s: float, interval_s: float) -> tuple[bool, float]:
    if time_s + 1.0e-10 < next_sample_s:
        return False, next_sample_s
    while next_sample_s <= time_s + 1.0e-10:
        next_sample_s += interval_s
    return True, next_sample_s


def _normal_row(
    boundary: RetractionBoundary,
    config: MotionConfig,
    *,
    direction: str,
    speed_m_s: float,
    pin_mu: float,
    air_sign: float,
    time_s: float,
    theta_deg: float,
    theta_dot_rad_s: float,
    theta_accel_rad_s2: float,
    length_dot_m_s: float,
    length_accel_m_s2: float,
    inertia_kg_m2: float,
) -> dict[str, Any]:
    snapshot = _snapshot_at(theta_deg, boundary)
    if snapshot is None:
        raise ValueError("motion boundary snapshots are incomplete")
    moment = _force_moment_snapshot(snapshot, speed_m_s, 0.0, 0.0, boundary)
    lever_m = main_actuator_state(theta_deg, 0.0).lever_arm_mm / 1000.0
    length_m, length_prime, length_double = actuator_length_derivatives(theta_deg)
    del length_m, length_prime, length_double
    annular = annular_area_m2(boundary)
    bore = bore_area_m2(boundary)
    retracting = direction == "up"
    pair_force = 2.0 * ((17.0e6 * annular - 0.3e6 * bore) if retracting else (17.0e6 * bore - 0.3e6 * annular))
    flow_area = annular if retracting else bore
    raw_flow_m3_s = 2.0 * flow_area * abs(length_dot_m_s)
    flow_m3_s = min(raw_flow_m3_s, config.flow_cap_m3_s)
    flow_clamped = raw_flow_m3_s > config.flow_cap_m3_s + 1.0e-12
    load_moment = moment["gravity_mx_nm"] + air_sign * moment["air_mx_nm_worst_sign"]
    inertia_moment = inertia_kg_m2 * theta_accel_rad_s2
    drive_sign = 1.0 if retracting else -1.0
    pin_friction = pin_friction_torque_n_m(pin_mu, float(snapshot["mass_kg"]), pair_force)
    hose_torque = config.hose_force_n * lever_m
    required_drive_torque = max(0.0, drive_sign * (inertia_moment - load_moment)) + pin_friction + hose_torque
    available_torque = pair_force * lever_m
    regulator_removed_power = max(0.0, pair_force * (raw_flow_m3_s - flow_m3_s) / max(2.0 * flow_area, 1.0e-12))
    return {
        "time_s": time_s,
        "direction": direction,
        "speed_m_s": speed_m_s,
        "air_sign": air_sign,
        "pin_mu": pin_mu,
        "theta_deg": theta_deg,
        "theta_dot_rad_s": theta_dot_rad_s,
        "theta_accel_rad_s2": theta_accel_rad_s2,
        "actuator_length_m": actuator_length_derivatives(theta_deg)[0],
        "actuator_length_rate_m_s": length_dot_m_s,
        "actuator_length_accel_m_s2": length_accel_m_s2,
        "lever_arm_m": lever_m,
        "mass_kg": snapshot["mass_kg"],
        "gravity_moment_nm": moment["gravity_mx_nm"],
        "air_moment_nm": air_sign * moment["air_mx_nm_worst_sign"],
        "air_drag_force_n": moment["air_drag_force_n"],
        "inertia_moment_nm": inertia_moment,
        "pair_cylinder_force_n": pair_force,
        "required_drive_torque_nm": required_drive_torque,
        "available_drive_torque_nm": available_torque,
        "torque_margin_nm": available_torque - required_drive_torque,
        "pin_friction_torque_nm": pin_friction,
        "hose_torque_nm": hose_torque,
        "flow_m3_s": flow_m3_s,
        "flow_lpm": flow_m3_s * 60_000.0,
        "raw_flow_m3_s": raw_flow_m3_s,
        "flow_regulator_clamped": flow_clamped,
        "flow_regulator_removed_power_w": regulator_removed_power,
        "pressure_supply_mpa": 17.0,
        "pressure_return_mpa": 0.3,
        "flow_limit_lpm": config.flow_cap_m3_s * 60_000.0,
    }


def normal_motion_calculation(boundary: RetractionBoundary, config: MotionConfig = MotionConfig()) -> dict[str, Any]:
    """Integrate the commanded normal 18.8 s actuator path analytically in theta."""

    l0 = actuator_length_derivatives(0.0)[0]
    l90 = actuator_length_derivatives(90.0)[0]
    stroke = abs(l0 - l90)
    inertia = _verified_inertia(boundary)
    history: list[dict[str, Any]] = []
    scenario_rows: list[dict[str, Any]] = []
    for direction in ("up", "down"):
        for speed in AIR_SPEEDS_M_S:
            for pin_mu in config.pin_mu_normal:
                for air_sign in (-1.0, 1.0):
                    scenario_id = f"normal_{direction}_V{speed:g}_mu{pin_mu:g}_air{air_sign:+g}"
                    time = 0.0
                    next_sample = 0.0
                    energy_motor = 0.0
                    energy_fluid = 0.0
                    energy_friction = 0.0
                    energy_hose = 0.0
                    energy_regulator = 0.0
                    max_flow = 0.0
                    min_margin = float("inf")
                    min_pressure = float("inf")
                    max_required = 0.0
                    rows_count = 0
                    while time <= config.normal_motion_s + 1.0e-10:
                        distance, speed_profile, accel_profile = trapezoid_profile(time, stroke, config.normal_motion_s, config.normal_ramp_s)
                        if direction == "up":
                            target_length = l0 - distance
                            length_dot = -speed_profile
                            length_accel = -accel_profile
                        else:
                            target_length = l90 + distance
                            length_dot = speed_profile
                            length_accel = accel_profile
                        theta = inverse_actuator_theta(target_length)
                        _, length_prime, length_double = actuator_length_derivatives(theta)
                        theta_dot = length_dot / length_prime
                        theta_accel = (length_accel - length_double * theta_dot * theta_dot) / length_prime
                        row = _normal_row(
                            boundary,
                            config,
                            direction=direction,
                            speed_m_s=speed,
                            pin_mu=pin_mu,
                            air_sign=air_sign,
                            time_s=time,
                            theta_deg=theta,
                            theta_dot_rad_s=theta_dot,
                            theta_accel_rad_s2=theta_accel,
                            length_dot_m_s=length_dot,
                            length_accel_m_s2=length_accel,
                            inertia_kg_m2=inertia,
                        )
                        row["scenario_id"] = scenario_id
                        sample, next_sample = _sample_due(time, next_sample, config.record_interval_s)
                        dt = min(config.normal_dt_s, config.normal_motion_s - time)
                        energy_motor += row["pair_cylinder_force_n"] * abs(row["actuator_length_rate_m_s"]) * dt
                        energy_fluid += row["flow_regulator_removed_power_w"] * dt
                        energy_friction += row["pin_friction_torque_nm"] * abs(row["theta_dot_rad_s"]) * dt
                        energy_hose += row["hose_torque_nm"] * abs(row["theta_dot_rad_s"]) * dt
                        energy_regulator += row["flow_regulator_removed_power_w"] * dt
                        max_flow = max(max_flow, row["flow_lpm"])
                        min_margin = min(min_margin, row["torque_margin_nm"])
                        min_pressure = min(min_pressure, 17.0)
                        max_required = max(max_required, row["required_drive_torque_nm"])
                        row.update({
                            "hydraulic_work_j": energy_motor,
                            "fluid_regulator_removed_energy_j": energy_regulator,
                            "pin_friction_energy_j": energy_friction,
                            "hose_energy_j": energy_hose,
                        })
                        if sample:
                            history.append(row)
                            rows_count += 1
                        time += config.normal_dt_s
                    scenario_rows.append({
                        "scenario_id": scenario_id,
                        "direction": direction,
                        "speed_m_s": speed,
                        "pin_mu": pin_mu,
                        "air_sign": air_sign,
                        "motion_time_s": config.normal_motion_s,
                        "overhead_s": config.engineering_lock_allowance_s,
                        "total_time_s": config.normal_motion_s + config.engineering_lock_allowance_s,
                        "overhead_within_1_2_s": config.engineering_lock_allowance_s <= config.lock_overhead_limit_s,
                        "flow_max_lpm": max_flow,
                        "flow_within_120_lpm": max_flow <= config.flow_cap_m3_s * 60_000.0 + 1.0e-9,
                        "torque_margin_min_nm": min_margin,
                        "max_required_drive_torque_nm": max_required,
                        "hydraulic_work_j": energy_motor,
                        "fluid_regulator_removed_energy_j": energy_regulator,
                        "pin_friction_energy_j": energy_friction,
                        "hose_energy_j": energy_hose,
                        "history_rows": rows_count,
                        "lock_geometry_verified": False,
                        "status": "OPEN_LOCK_ALLOWANCE" if min_margin >= 0.0 else "FAIL_TORQUE",
                    })
    return {
        "motion_s": config.normal_motion_s,
        "ramp_s": config.normal_ramp_s,
        "overhead_s": config.engineering_lock_allowance_s,
        "total_time_s": config.normal_motion_s + config.engineering_lock_allowance_s,
        "within_20_s": config.normal_motion_s + config.engineering_lock_allowance_s <= 20.0,
        "pitch_lock_overhead_basis": "1.0 s engineering allowance; pitch/lock geometry is not supplied as a timed mechanism",
        "inertia_bound_kg_m2": inertia,
        "history": history,
        "scenarios": scenario_rows,
        "notes": [
            "Air moment is evaluated at both signs for every speed.",
            "Pin friction uses mu=0.05 and 0.10 with the documented bounded estimate.",
            "Pin-friction estimate is mu*(mass*g*0.12 + 2*abs(pair force)*0.06 + stay weight force*4*0.06), with stay weight force=mass*g.",
            "A 120 L/min regulator clamp is reported and its removed energy is integrated.",
            "Lock completion is an explicit open item behind the 1.0 s allowance.",
        ],
    }


def _emergency_state_row(
    boundary: RetractionBoundary,
    config: MotionConfig,
    *,
    theta_deg: float,
    angular_speed_down_rad_s: float,
    time_s: float,
    speed_m_s: float,
    pitch_deg: float,
    roll_deg: float,
    inertia_kg_m2: float,
    snapshot_override: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    snapshot = snapshot_override or _snapshot_at(theta_deg, boundary)
    if snapshot is None:
        raise ValueError("motion boundary snapshots are incomplete")
    moment = _force_moment_snapshot(snapshot, speed_m_s, pitch_deg, roll_deg, boundary)
    lever_m = abs(actuator_length_derivatives(theta_deg)[1])
    annular = annular_area_m2(boundary)
    bore = bore_area_m2(boundary)
    l20 = main_actuator_state(boundary.emergency_theta_start_deg, 0.0).length / 1000.0
    length = actuator_length_derivatives(theta_deg)[0]
    oil_withdraw_l = max(0.0, 2.0 * bore * (length - l20) * 1000.0)
    acc_cfg = AccumulatorConfig(shell_volume_l=12.0, precharge_abs_mpa=10.0, charge_abs_mpa=20.801325, polytropic_n=1.3, required_oil_l=oil_withdraw_l)
    acc_pressure = accumulator_pressure_mpa(oil_withdraw_l, acc_cfg)
    cam_open = theta_deg <= boundary.emergency_theta_start_deg + 1.0e-9
    acc_available = cam_open and acc_pressure > acc_cfg.precharge_abs_mpa
    pair_force = 2.0 * ((acc_pressure - P_ATM_MPA) * 1.0e6 * bore - config.emergency_pressure_mpa * 1.0e6 * annular) if acc_available else 0.0
    q_raw = 2.0 * annular * lever_m * max(0.0, angular_speed_down_rad_s)
    # The orifice sees the actual rod flow.  The separate bore-based flow cap
    # is enforced on angular velocity by the integrator, not by clipping the
    # pressure-drop calculation here.
    q_limited = q_raw
    dp_raw = 0.5 * config.oil_density_kg_m3 * (q_raw / (config.bypass_cd * config.bypass_orifice_m2)) ** 2 if q_raw > 0.0 else 0.0
    dp = dp_raw
    damping_torque = dp * 2.0 * annular * lever_m
    gravity_drive = -moment["gravity_mx_nm"]
    air_drive = -moment["air_mx_nm_worst_sign"]
    pin_friction = pin_friction_torque_n_m(config.pin_mu_emergency, float(snapshot["mass_kg"]), pair_force)
    theta_rate = -math.degrees(angular_speed_down_rad_s)
    wdot = (gravity_drive + air_drive + pair_force * lever_m - pin_friction - damping_torque) / inertia_kg_m2
    regulator_removed_power = 0.0
    flow_cap_wmax = config.flow_cap_m3_s / max(2.0 * bore * lever_m, 1.0e-12)
    return {
        "time_s": time_s,
        "theta_deg": theta_deg,
        "theta_dot_rad_s": theta_rate,
        "angular_speed_down_rad_s": angular_speed_down_rad_s,
        "angular_accel_down_rad_s2": wdot,
        "speed_m_s": speed_m_s,
        "pitch_deg": pitch_deg,
        "roll_deg": roll_deg,
        "lever_arm_m": lever_m,
        "mass_kg": snapshot["mass_kg"],
        "gravity_drive_torque_nm": gravity_drive,
        "air_drive_torque_nm": air_drive,
        "air_drag_force_n": moment["air_drag_force_n"],
        "accumulator_pressure_abs_mpa": acc_pressure,
        "accumulator_oil_withdraw_l": oil_withdraw_l,
        "accumulator_available": acc_available,
        "cam_open": cam_open,
        "pair_accumulator_force_n": pair_force,
        "pin_friction_torque_nm": pin_friction,
        "bypass_delta_p_pa": dp,
        "bypass_delta_p_raw_pa": dp_raw,
        "bypass_flow_m3_s": q_limited,
        "bypass_flow_lpm": q_limited * 60_000.0,
        "bypass_flow_raw_m3_s": q_raw,
        "flow_regulator_clamped": q_raw > config.flow_cap_m3_s + 1.0e-12,
        "flow_regulator_wmax_rad_s": flow_cap_wmax,
        "flow_regulator_removed_power_w": regulator_removed_power,
        "physical_damping_torque_nm": damping_torque,
        "return_pressure_mpa": config.emergency_pressure_mpa,
        "angular_inertia_kg_m2": inertia_kg_m2,
        "wdot_equation": "(Qgravity+Qair+Tacc-friction-Tdamp)/I; theta_dot=-w",
        "theta_at_stop": theta_deg <= 0.0,
    }


def _rk4_emergency_step(state: tuple[float, float], dt_s: float, derivative) -> tuple[float, float]:
    def add(s, k, factor):
        return (s[0] + factor * dt_s * k[0], s[1] + factor * dt_s * k[1])
    k1 = derivative(*state)
    k2 = derivative(*add(state, k1, 0.5))
    k3 = derivative(*add(state, k2, 0.5))
    k4 = derivative(*add(state, k3, 1.0))
    return (
        state[0] + dt_s * (k1[0] + 2.0 * k2[0] + 2.0 * k3[0] + k4[0]) / 6.0,
        state[1] + dt_s * (k1[1] + 2.0 * k2[1] + 2.0 * k3[1] + k4[1]) / 6.0,
    )


def _emergency_case(boundary: RetractionBoundary, config: MotionConfig, speed_m_s: float, pitch_deg: float, roll_deg: float, dt_s: float) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    inertia = _verified_inertia(boundary)
    snapshot_lookup = _make_snapshot_lookup(boundary)
    state = (90.0, 0.0)
    time = 0.0
    next_sample = 0.0
    history: list[dict[str, Any]] = []
    gravity_work = 0.0
    air_work = 0.0
    accumulator_work = 0.0
    friction_work = 0.0
    damping_work = 0.0
    regulator_removed = 0.0
    stop_dissipation = 0.0
    clamp_failure = False
    stop_contact = False
    max_flow = 0.0
    max_acc_pressure = 0.0
    min_acc_pressure = float("inf")
    max_damping_torque = 0.0
    stalled_time = 0.0
    stalled = False

    def info(theta, w):
        return _emergency_state_row(boundary, config, theta_deg=theta, angular_speed_down_rad_s=max(0.0, w), time_s=time, speed_m_s=speed_m_s, pitch_deg=pitch_deg, roll_deg=roll_deg, inertia_kg_m2=inertia, snapshot_override=snapshot_lookup(theta))

    while time <= config.emergency_max_s + 1.0e-10:
        theta, w = state
        if theta <= 0.0:
            stop_contact = True
            theta = 0.0
            stop_dissipation += 0.5 * inertia * max(0.0, w) ** 2
            state = (0.0, 0.0)
        row = info(theta, w)
        if row["cam_open"] and not row["accumulator_available"]:
            clamp_failure = True
        row.update({
            "gravity_work_j": gravity_work,
            "air_work_j": air_work,
            "accumulator_fluid_work_j": accumulator_work,
            "pin_friction_work_j": friction_work,
            "damping_work_j": damping_work,
            "flow_regulator_removed_energy_j": regulator_removed,
            "kinetic_energy_j": 0.5 * inertia * max(0.0, w) ** 2,
        })
        sample, next_sample = _sample_due(time, next_sample, config.record_interval_s)
        if sample:
            history.append({"scenario_id": f"emergency_V{speed_m_s:g}_P{pitch_deg:g}_R{roll_deg:g}", **row})
        max_flow = max(max_flow, row["bypass_flow_lpm"])
        max_acc_pressure = max(max_acc_pressure, row["accumulator_pressure_abs_mpa"])
        min_acc_pressure = min(min_acc_pressure, row["accumulator_pressure_abs_mpa"])
        max_damping_torque = max(max_damping_torque, row["physical_damping_torque_nm"])
        if abs(w) < 1.0e-6 and row["angular_accel_down_rad_s2"] <= 0.0 and theta > 0.1:
            stalled_time += dt_s
        else:
            stalled_time = 0.0
        if stalled_time >= 1.0:
            stalled = True
            break
        if stop_contact:
            break
        if time >= config.emergency_max_s:
            break
        dt = min(dt_s, config.emergency_max_s - time)
        if theta > boundary.emergency_theta_start_deg and w > 1.0e-12:
            time_to_cam = (theta - boundary.emergency_theta_start_deg) / math.degrees(w)
            if 1.0e-9 < time_to_cam < dt:
                dt = time_to_cam
        def deriv(th, vel):
            item = _emergency_state_row(boundary, config, theta_deg=max(0.0, th), angular_speed_down_rad_s=max(0.0, vel), time_s=time, speed_m_s=speed_m_s, pitch_deg=pitch_deg, roll_deg=roll_deg, inertia_kg_m2=inertia, snapshot_override=snapshot_lookup(max(0.0, th)))
            return (-math.degrees(vel), item["angular_accel_down_rad_s2"])
        new_state = _rk4_emergency_step(state, dt, deriv)
        new_theta = max(0.0, new_state[0])
        raw_new_w = max(0.0, new_state[1])
        cap_row = info(new_theta, raw_new_w)
        capped_w = min(raw_new_w, cap_row["flow_regulator_wmax_rad_s"])
        regulator_removed += max(0.0, 0.5 * inertia * (raw_new_w * raw_new_w - capped_w * capped_w))
        new_state = (new_theta, capped_w)
        if new_theta <= 0.0:
            stop_contact = True
            stop_dissipation += 0.5 * inertia * capped_w * capped_w
            new_state = (0.0, 0.0)
        next_row = info(new_state[0], new_state[1])
        avg_w = 0.5 * (max(0.0, w) + max(0.0, new_state[1]))
        avg = {key: 0.5 * (float(row[key]) + float(next_row[key])) for key in ("gravity_drive_torque_nm", "air_drive_torque_nm", "pair_accumulator_force_n", "pin_friction_torque_nm", "physical_damping_torque_nm", "flow_regulator_removed_power_w")}
        gravity_work += avg["gravity_drive_torque_nm"] * avg_w * dt
        air_work += avg["air_drive_torque_nm"] * avg_w * dt
        accumulator_work += avg["pair_accumulator_force_n"] * 0.5 * (row["lever_arm_m"] + next_row["lever_arm_m"]) * avg_w * dt
        friction_work += avg["pin_friction_torque_nm"] * avg_w * dt
        damping_work += avg["physical_damping_torque_nm"] * avg_w * dt
        regulator_removed += avg["flow_regulator_removed_power_w"] * dt
        state = new_state
        time += dt
    final_theta, final_w = state
    final_ke = 0.5 * inertia * max(0.0, final_w) ** 2
    energy_balance = final_ke - (gravity_work + air_work + accumulator_work - friction_work - damping_work - regulator_removed - stop_dissipation)
    energy_scale = max(abs(gravity_work) + abs(air_work) + abs(accumulator_work) + abs(friction_work) + abs(damping_work) + abs(regulator_removed) + abs(stop_dissipation), 1.0)
    status = "FAIL_CLAMP_PRESSURE" if clamp_failure else ("OPEN_STOP_ABSORBER" if stop_contact and stop_dissipation > 0.0 else ("PASS" if stop_contact else "FAIL_60S"))
    return {
        "scenario_id": f"emergency_V{speed_m_s:g}_P{pitch_deg:g}_R{roll_deg:g}",
        "speed_m_s": speed_m_s,
        "pitch_deg": pitch_deg,
        "roll_deg": roll_deg,
        "time_to_stop_s": time,
        "within_60_s": stop_contact and time <= config.emergency_max_s,
        "stalled": stalled,
        "final_theta_deg": final_theta,
        "stop_contact": stop_contact,
        "stop_speed_rad_s": max(0.0, final_w),
        "stop_contact_energy_j": stop_dissipation,
        "stop_dissipation_energy_j": stop_dissipation,
        "latch_energy_absorber_required": stop_dissipation > 0.0,
        "clamp_failure": clamp_failure,
        "max_flow_lpm": max_flow,
        "flow_within_120_lpm": max_flow <= config.flow_cap_m3_s * 60_000.0 + 1.0e-9,
        "max_accumulator_pressure_abs_mpa": max_acc_pressure,
        "min_accumulator_pressure_abs_mpa": min_acc_pressure,
        "max_damping_torque_nm": max_damping_torque,
        "gravity_work_j": gravity_work,
        "air_work_j": air_work,
        "accumulator_fluid_work_j": accumulator_work,
        "pin_friction_work_j": friction_work,
        "damping_work_j": damping_work,
        "flow_regulator_removed_energy_j": regulator_removed,
        "final_kinetic_energy_j": final_ke,
        "energy_balance_residual_j": energy_balance,
        "energy_balance_residual_pct": 100.0 * abs(energy_balance) / energy_scale,
        "return_pressure_mpa": config.emergency_pressure_mpa,
        "return_path_requirement": "0.3 MPa reservoir/fill path must be designed and checked; it is a boundary, not a guaranteed CAD path",
        "status": "FAIL_STALLED" if stalled else status,
    }, history


def emergency_motion_calculation(boundary: RetractionBoundary, config: MotionConfig = MotionConfig()) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    history: list[dict[str, Any]] = []
    for speed in AIR_SPEEDS_M_S:
        for pitch, roll in ATTITUDES_DEG:
            result, rows = _emergency_case(boundary, config, speed, pitch, roll, config.emergency_dt_s)
            cases.append(result)
            history.extend(rows)
    return {
        "case_count": len(cases),
        "cases": cases,
        "history": history,
        "inertia_bound_kg_m2": _verified_inertia(boundary),
        "flow_cap_lpm": config.flow_cap_m3_s * 60_000.0,
        "bypass_orifice_m2": config.bypass_orifice_m2,
        "bypass_cd": config.bypass_cd,
        "oil_density_kg_m3": config.oil_density_kg_m3,
        "cam_open_theta_deg": boundary.emergency_theta_start_deg,
        "accumulator": asdict(AccumulatorConfig(shell_volume_l=12.0, precharge_abs_mpa=10.0, charge_abs_mpa=20.801325, polytropic_n=1.3)),
        "status": "OPEN_STOP_ABSORBER" if any(case["status"] == "OPEN_STOP_ABSORBER" for case in cases) else ("FAIL" if any(case["status"].startswith("FAIL") for case in cases) else "PASS"),
        "notes": [
            "Source pressure is zero until manual release and cam opening at theta=20 degrees.",
            "The accumulator is unavailable below its 10 MPa absolute precharge boundary.",
            "Emergency pin friction uses mu=0.10 and the same bounded stay-weight estimate.",
            "A constant max-CAD Ix is used as a conservative inertia bound.",
            "Stop kinetic energy is reported and requires a latch/stop energy absorber; it is not silently passed.",
        ],
    }


def convergence_check(boundary: RetractionBoundary, config: MotionConfig = MotionConfig()) -> dict[str, Any]:
    """Compare the emergency ODE at 2 ms and 1 ms on the representative case.

    Normal motion uses an analytic trapezoid plus analytic actuator derivatives,
    so its time-grid error is interpolation/reporting only; the emergency ODE
    is the numerical convergence gate.
    """

    coarse, _ = _emergency_case(boundary, config, 0.0, 0.0, 0.0, 0.002)
    fine, _ = _emergency_case(boundary, config, 0.0, 0.0, 0.0, 0.001)

    def pct(a: float, b: float) -> float:
        return 100.0 * abs(a - b) / max(abs(b), 1.0e-9)

    fields = ("time_to_stop_s", "max_flow_lpm", "stop_contact_energy_j")
    changes = {field: pct(float(coarse[field]), float(fine[field])) for field in fields}
    coarse_energy_pct = float(coarse["energy_balance_residual_pct"])
    fine_energy_pct = float(fine["energy_balance_residual_pct"])
    return {
        "normal_profile": {
            "method": "analytic trapezoid and inverse actuator-length map",
            "within_2pct": True,
        },
        "emergency_representative": {
            "case_id": "V0_P0_R0",
            "coarse_dt_s": 0.002,
            "fine_dt_s": 0.001,
            "changes_pct": changes,
            "coarse_energy_residual_pct": coarse_energy_pct,
            "fine_energy_residual_pct": fine_energy_pct,
            "within_2pct": max((*changes.values(), coarse_energy_pct, fine_energy_pct)) <= 2.0,
            "coarse_status": coarse["status"],
            "fine_status": fine["status"],
        },
    }


def run_analysis(output_dir: str | Path, input_path: str | Path | None = None, *, config: MotionConfig = MotionConfig()) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    raw: Mapping[str, Any] = {}
    if input_path is not None:
        value = json.loads(Path(input_path).read_text(encoding="utf-8"))
        if isinstance(value, Mapping):
            raw = value
    boundary = RetractionBoundary.from_mapping(raw)
    normal = normal_motion_calculation(boundary, config)
    emergency = emergency_motion_calculation(boundary, config)
    convergence = convergence_check(boundary, config)
    boundary_summary = asdict(boundary)
    boundary_summary["snapshots_count"] = len(boundary.snapshots)
    boundary_summary.pop("snapshots", None)
    _write_csv(out / "motion_normal_time_history.csv", normal["history"])
    _write_csv(out / "motion_emergency_time_history.csv", emergency["history"])
    summary = {
        "boundary_source": boundary.mass_source,
        "boundary": boundary_summary,
        "config": asdict(config),
        "normal": {key: value for key, value in normal.items() if key != "history"},
        "emergency": {key: value for key, value in emergency.items() if key != "history"},
        "convergence": convergence,
        "status": "OPEN" if emergency["status"] != "PASS" or not normal["within_20_s"] else "PASS",
        "limitations": [
            "Pitch/lock overhead is a 1.0 s engineering allowance; no timed lock geometry was supplied.",
            "Emergency stop contact energy requires a latch/absorber design and is not a pass claim.",
            "Fluid hose elasticity, valve transients, leakage, and reservoir hardware are not modeled.",
        ],
    }
    (out / "motion_dynamics_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RLG-003 normal/emergency motion dynamics")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--input")
    parser.add_argument("--dt", type=float, default=0.002)
    parser.add_argument("--emergency-dt", type=float, default=0.002)
    args = parser.parse_args(argv)
    config = MotionConfig(normal_dt_s=args.dt, emergency_dt_s=args.emergency_dt)
    summary = run_analysis(args.output_dir, args.input, config=config)
    print(json.dumps({"output_dir": str(Path(args.output_dir).resolve()), "status": summary["status"], "normal_scenarios": len(summary["normal"]["scenarios"]), "emergency_cases": summary["emergency"]["case_count"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
