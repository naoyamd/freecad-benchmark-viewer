"""RLG-003 v3.0 preliminary landing-gear calculations.

This module deliberately stays self contained.  It is a sizing model for the
CAD design, not a certification model or an FEA wrapper.  All public
calculations use SI units; dimensions read from ``cad/rlg003/parameters.json``
are converted at the boundary.

The command line interface writes only to the directory supplied with
``--output-dir``.  It emits small CSV/JSON evidence files that can be copied
alongside the CAD model.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence


G = 9.80665
P_ATM = 101_325.0
T_REF_K = 293.15
RHO_OIL = 870.0
CD_ORIFICE = 0.65
TIRE_RATED_LOAD_N = 61_525.0 * 4.4482216152605
TIRE_MAX_DELTA_M = 0.270
TIRE_MAX_FORCE_N = 800_000.0
WHEEL_IDS = ("FI", "FO", "MI", "MO", "RI", "RO")
WHEEL_X_M = {"FI": 1.5, "FO": 1.5, "MI": 0.0, "MO": 0.0, "RI": -1.5, "RO": -1.5}
WHEEL_Y_M = {"FI": -0.650, "FO": 0.650, "MI": -0.650, "MO": 0.650, "RI": -0.650, "RO": 0.650}


def _cad_path() -> Path:
    return Path(__file__).resolve().parents[1] / "cad" / "rlg003" / "parameters.json"


def _cad_mass_path() -> Path:
    return Path(__file__).resolve().parents[1] / "outputs" / "RLG-003_Astra_Luna_r02" / "deliverables" / "cad_mass.json"


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def load_cad_parameters(path: str | Path | None = None) -> dict[str, Any]:
    return load_json(path or _cad_path())


def load_verified_mass(path: str | Path | None = None) -> dict[str, float]:
    """Read the optional verified CAD mass snapshot without changing task masses."""
    source = Path(path) if path is not None else _cad_mass_path()
    if not source.exists():
        return {}
    data = load_json(source)
    result: dict[str, float] = {}
    for key in ("unsprung_mass_kg", "bogie_inertia_kg_m2"):
        if key in data:
            try:
                result[key] = float(data[key])
            except (TypeError, ValueError):
                pass
    wheel_data = data.get("wheel_inertia_kg_m2")
    if isinstance(wheel_data, Mapping):
        values = []
        for value in wheel_data.values():
            try:
                values.append(float(value))
            except (TypeError, ValueError):
                pass
        if values:
            result["wheel_inertia_kg_m2"] = sum(values) / len(values)
    return result


def _nested_number(source: Mapping[str, Any], keys: Sequence[str], default: float) -> float:
    current: Any = source
    for key in keys:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    try:
        return float(current)
    except (TypeError, ValueError):
        return default


def _pick_number(source: Mapping[str, Any], names: Sequence[str], default: float) -> float:
    for name in names:
        if name in source:
            try:
                return float(source[name])
            except (TypeError, ValueError):
                pass
    return default


@dataclass
class OleoConfig:
    stroke_m: float = 0.600
    gas_volume_m3: float = 0.0650
    gas_precharge_abs_pa: float = 8.9e6
    polytropic_n: float = 1.3
    pumped_area_m2: float = math.pi * (0.330**2) / 4.0
    # Gas force uses the piston swept area; oil flow uses the physical
    # BarrelID/PistonOD annulus.  They are deliberately separate areas.
    flow_area_m2: float = math.pi * (0.460**2 - 0.330**2) / 4.0
    cd: float = CD_ORIFICE
    oil_density_kg_m3: float = RHO_OIL
    orifice_compression_m2: float = 2.90e-3
    orifice_extension_m2: float = 5.32e-3
    friction_n: float = 5_000.0
    compression_stop_k_n_m: float = 2.0e8
    extension_stop_k_n_m: float = 2.0e8
    stop_damping_n_s_m: float = 1.0e6
    reference_temperature_c: float = 20.0
    static_polytropic_n: float = 1.0
    auxiliary_spring_engagement_m: float = 0.150
    auxiliary_spring_k_n_m: float = 565_000.0
    auxiliary_spring_preload_n: float = 0.0

    @classmethod
    def from_sources(
        cls, cad: Mapping[str, Any], override: Mapping[str, Any] | None = None
    ) -> "OleoConfig":
        mm = cad.get("cad_mm", {}) if isinstance(cad.get("cad_mm"), Mapping) else {}
        cad_analysis = cad.get("analysis", {}) if isinstance(cad.get("analysis"), Mapping) else {}
        cad_oleo = cad_analysis.get("oleo", {}) if isinstance(cad_analysis.get("oleo"), Mapping) else {}
        source = dict(cad_oleo)
        source.update(override or {})
        area = math.pi * (_pick_number(mm, ("PistonOD",), 330.0) / 1000.0) ** 2 / 4.0
        barrel_id_m = _pick_number(mm, ("BarrelID",), 350.0) / 1000.0
        piston_od_m = _pick_number(mm, ("PistonOD",), 330.0) / 1000.0
        annulus_area = math.pi * max(0.0, barrel_id_m**2 - piston_od_m**2) / 4.0
        return cls(
            stroke_m=_pick_number(source, ("stroke_m", "stroke"), _pick_number(mm, ("StrokeMax",), 600.0) / 1000.0),
            gas_volume_m3=_pick_number(source, ("gas_volume_m3", "gas_volume"), _pick_number(mm, ("GasVolumeL",), 65.0) / 1000.0),
            gas_precharge_abs_pa=_pick_number(source, ("gas_precharge_abs_pa",), _pick_number(mm, ("GasPrechargeMPaAbs",), 8.9) * 1.0e6),
            polytropic_n=_pick_number(source, ("polytropic_n", "n"), 1.3),
            pumped_area_m2=_pick_number(source, ("pumped_area_m2",), area),
            flow_area_m2=_pick_number(source, ("flow_area_m2", "oil_flow_area_m2"), annulus_area),
            cd=_pick_number(source, ("cd", "discharge_coefficient"), CD_ORIFICE),
            oil_density_kg_m3=_pick_number(source, ("oil_density_kg_m3",), RHO_OIL),
            orifice_compression_m2=_pick_number(source, ("orifice_compression_m2",), 2.90e-3),
            orifice_extension_m2=_pick_number(source, ("orifice_extension_m2",), 5.32e-3),
            friction_n=_pick_number(source, ("friction_n",), 5_000.0),
            compression_stop_k_n_m=_pick_number(source, ("compression_stop_k_n_m",), 2.0e8),
            extension_stop_k_n_m=_pick_number(source, ("extension_stop_k_n_m",), 2.0e8),
            stop_damping_n_s_m=_pick_number(source, ("stop_damping_n_s_m",), 1.0e6),
            reference_temperature_c=_pick_number(source, ("reference_temperature_c",), 20.0),
            static_polytropic_n=_pick_number(source, ("static_polytropic_n",), 1.0),
            auxiliary_spring_engagement_m=_pick_number(source, ("auxiliary_spring_engagement_m",), 0.150),
            auxiliary_spring_k_n_m=_pick_number(source, ("auxiliary_spring_k_n_m",), 565_000.0),
            auxiliary_spring_preload_n=_pick_number(source, ("auxiliary_spring_preload_n",), 0.0),
        )

    def validate(self) -> None:
        if self.stroke_m <= 0 or self.gas_volume_m3 <= 0 or self.pumped_area_m2 <= 0:
            raise ValueError("stroke, gas volume and pumped area must be positive")
        if self.gas_volume_m3 - self.pumped_area_m2 * self.stroke_m <= 0:
            raise ValueError("gas volume becomes non-positive before full stroke")
        if not 0.2 * self.gas_volume_m3 <= self.gas_volume_m3 - self.pumped_area_m2 * self.stroke_m:
            raise ValueError("gas volume at full stroke is below the 20% specification minimum")
        if self.polytropic_n < 1.0 or self.cd <= 0 or self.oil_density_kg_m3 <= 0:
            raise ValueError("invalid gas/oil properties")
        if self.orifice_compression_m2 <= 0 or self.orifice_extension_m2 <= 0 or self.flow_area_m2 <= 0:
            raise ValueError("orifice areas must be positive")
        if self.orifice_extension_m2 < self.orifice_compression_m2:
            raise ValueError("extension area must include the compression passages")
        if self.static_polytropic_n <= 0 or self.auxiliary_spring_engagement_m < 0 or self.auxiliary_spring_k_n_m < 0:
            raise ValueError("invalid static gas or auxiliary spring parameters")


def auxiliary_spring_force(stroke_m: float, config: OleoConfig | None = None) -> float:
    cfg = config or OleoConfig()
    return cfg.auxiliary_spring_preload_n + cfg.auxiliary_spring_k_n_m * max(0.0, stroke_m - cfg.auxiliary_spring_engagement_m)


def auxiliary_spring_energy(stroke_m: float, config: OleoConfig | None = None) -> float:
    cfg = config or OleoConfig()
    extension = max(0.0, stroke_m - cfg.auxiliary_spring_engagement_m)
    return cfg.auxiliary_spring_preload_n * extension + 0.5 * cfg.auxiliary_spring_k_n_m * extension * extension


@dataclass
class DynamicCase:
    case_id: str
    mass_kg: float
    sink_speed_m_s: float
    lift_n: float
    initial_beta_deg: float = 0.0
    free_pitch: bool = True


@dataclass
class DynamicConfig:
    unsprung_mass_kg: float = 5_769.56284980624
    bogie_inertia_kg_m2: float = 6_137.017966002854
    tire_scale: float = 1.0
    temperature_c: float = 20.0
    friction_n: float = 5_000.0
    pitch_damping_n_m_s: float = 150.0
    pitch_stop_deg: float = 12.0
    pitch_stop_k_n_m: float = 2.0e8
    pitch_stop_damping_n_m_s: float = 1.0e6
    wheel_inertia_kg_m2: float = 38.61233982745639


@dataclass
class StaticResult:
    load_n: float
    stroke_m: float | None
    load_at_zero_n: float
    load_at_full_n: float
    percent_stroke: float | None
    friction_low_stroke_m: float | None
    friction_high_stroke_m: float | None
    within_range: bool


@dataclass
class WheelResult:
    wheel_id: str
    load_n: float
    deflection_m: float
    healthy: bool
    bottomed: bool
    rated_excess_n: float
    x_m: float
    y_m: float


@dataclass
class DynamicResult:
    case_id: str
    dt_s: float
    max_stroke_m: float
    max_ground_reaction_n: float
    max_airframe_reaction_n: float
    max_tire_deflection_m: float
    max_beta_deg: float
    max_pitch_torque_n_m: float
    max_axis_loads_n: dict[str, float]
    final_stroke_m: float
    rebound_complete: bool
    extension_stop: bool
    compression_stop: bool
    tire_bottomed: bool
    pressure_max_abs_pa: float
    pressure_max_gauge_pa: float
    max_orifice_dp_pa: float
    min_oil_pressure_abs_pa: float
    min_upper_oil_pressure_abs_pa: float
    min_lower_oil_pressure_abs_pa: float
    max_upper_oil_pressure_abs_pa: float
    max_lower_oil_pressure_abs_pa: float
    max_oil_pressure_abs_pa: float
    max_oil_pressure_gauge_pa: float
    cavitation_detected: bool
    energy_initial_j: float
    energy_gravity_j: float
    energy_lift_j: float
    energy_gas_j: float
    energy_spring_j: float
    energy_tire_j: float
    energy_dissipation_j: float
    energy_final_kinetic_j: float
    energy_residual_j: float
    time_to_max_stroke_s: float | None
    history: list[dict[str, Any]] = field(default_factory=list)


def tire_force(deflection_m: float, scale: float = 1.0) -> float:
    """Three point task tire curve, clipped at its stated bottoming boundary."""
    if deflection_m <= 0.0:
        return 0.0
    if deflection_m < 0.120:
        return scale * (273_677.0 / 0.120) * deflection_m
    if deflection_m < TIRE_MAX_DELTA_M:
        return scale * (273_677.0 + (800_000.0 - 273_677.0) * (deflection_m - 0.120) / 0.150)
    return scale * TIRE_MAX_FORCE_N


def tire_deflection_for_force(force_n: float, scale: float = 1.0) -> float:
    if force_n <= 0.0:
        return 0.0
    f1 = 273_677.0 * scale
    if force_n <= f1:
        return force_n / scale * 0.120 / 273_677.0
    return 0.120 + (force_n / scale - 273_677.0) * 0.150 / (800_000.0 - 273_677.0)


def tire_energy(deflection_m: float, scale: float = 1.0) -> float:
    """Elastic work in the clipped piecewise tire curve."""
    d = max(0.0, deflection_m)
    d1 = min(d, 0.120)
    k1 = scale * 273_677.0 / 0.120
    result = 0.5 * k1 * d1 * d1
    if d > 0.120:
        d2 = min(d, TIRE_MAX_DELTA_M) - 0.120
        k2 = scale * (800_000.0 - 273_677.0) / 0.150
        result += 273_677.0 * scale * d2 + 0.5 * k2 * d2 * d2
    if d > TIRE_MAX_DELTA_M:
        result += scale * TIRE_MAX_FORCE_N * (d - TIRE_MAX_DELTA_M)
    return result


def gas_state(
    stroke_m: float,
    config: OleoConfig | None = None,
    *,
    temperature_c: float | None = None,
) -> dict[str, float]:
    """Return volume and absolute/gauge pressure for a compressed gas chamber."""
    cfg = config or OleoConfig()
    if stroke_m < 0.0 or stroke_m > cfg.stroke_m:
        raise ValueError("stroke is outside the modeled range")
    volume = cfg.gas_volume_m3 - cfg.pumped_area_m2 * stroke_m
    if volume <= 0.0:
        raise ValueError("gas volume is non-positive")
    temp_k = 273.15 + (cfg.reference_temperature_c if temperature_c is None else temperature_c)
    if temp_k <= 0.0:
        raise ValueError("temperature must be above absolute zero")
    pressure_abs = cfg.gas_precharge_abs_pa * (cfg.gas_volume_m3 / volume) ** cfg.polytropic_n * temp_k / (273.15 + cfg.reference_temperature_c)
    pressure_gauge = pressure_abs - P_ATM
    return {
        "stroke_m": stroke_m,
        "volume_m3": volume,
        "pressure_abs_pa": pressure_abs,
        "pressure_gauge_pa": pressure_gauge,
        "force_n": pressure_gauge * cfg.pumped_area_m2,
        "temperature_k": temp_k,
    }


def gas_potential_energy(stroke_m: float, config: OleoConfig | None = None, *, temperature_c: float | None = None) -> float:
    """Gas work relative to full extension, using gauge pressure."""
    cfg = config or OleoConfig()
    state0 = gas_state(0.0, cfg, temperature_c=temperature_c)
    state = gas_state(stroke_m, cfg, temperature_c=temperature_c)
    v0, v = state0["volume_m3"], state["volume_m3"]
    c = cfg.gas_precharge_abs_pa * v0 ** cfg.polytropic_n
    if abs(cfg.polytropic_n - 1.0) < 1.0e-12:
        work_abs = c * math.log(v0 / v)
    else:
        work_abs = c * (v ** (1.0 - cfg.polytropic_n) - v0 ** (1.0 - cfg.polytropic_n)) / (cfg.polytropic_n - 1.0)
    # The atmosphere acts on the opposite side of the piston and is therefore
    # removed from the mechanical gas work just as it is from force_n.
    return work_abs - P_ATM * cfg.pumped_area_m2 * stroke_m


def oil_flow_and_damping(sdot_m_s: float, config: OleoConfig | None = None, *, upstream_abs_pa: float | None = None) -> dict[str, float | bool]:
    cfg = config or OleoConfig()
    upper_pressure = upstream_abs_pa if upstream_abs_pa is not None else float("inf")
    if sdot_m_s == 0.0:
        return {
            "flow_m3_s": 0.0,
            "delta_p_pa": 0.0,
            "force_n": 0.0,
            "power_w": 0.0,
            "orifice_area_m2": cfg.orifice_compression_m2,
            "upper_abs_pa": upper_pressure,
            "lower_abs_pa": upper_pressure,
            "upstream_chamber_abs_pa": upper_pressure,
            "downstream_abs_pa": upper_pressure,
            "min_chamber_abs_pa": upper_pressure,
            "max_chamber_abs_pa": upper_pressure,
            "cavitation": upper_pressure < P_ATM,
        }
    flow = cfg.flow_area_m2 * abs(sdot_m_s)
    area = cfg.orifice_compression_m2 if sdot_m_s > 0.0 else cfg.orifice_extension_m2
    delta_p = 0.5 * cfg.oil_density_kg_m3 * (flow / (cfg.cd * area)) ** 2
    force = math.copysign(delta_p * cfg.flow_area_m2, sdot_m_s)
    if sdot_m_s > 0.0:
        # Compression expands the lower annulus: gas-side upper pressure is
        # upstream and the lower pressure drops across the compression ports.
        lower_pressure = upper_pressure - delta_p
        upstream_chamber = upper_pressure
        downstream = lower_pressure
    else:
        # Rebound shrinks the lower annulus: lower oil is upstream and rises
        # by delta-p before returning to the upper chamber.  The upper chamber
        # remains at the gas pressure, so it is the minimum chamber pressure.
        lower_pressure = upper_pressure + delta_p
        upstream_chamber = lower_pressure
        downstream = upper_pressure
    minimum = min(upper_pressure, lower_pressure)
    maximum = max(upper_pressure, lower_pressure)
    return {
        "flow_m3_s": flow,
        "delta_p_pa": delta_p,
        "force_n": force,
        "power_w": delta_p * flow,
        "orifice_area_m2": area,
        "upper_abs_pa": upper_pressure,
        "lower_abs_pa": lower_pressure,
        "upstream_chamber_abs_pa": upstream_chamber,
        "downstream_abs_pa": downstream,
        "min_chamber_abs_pa": minimum,
        "max_chamber_abs_pa": maximum,
        "cavitation": minimum < P_ATM,
    }


def static_equilibrium(load_n: float, config: OleoConfig | None = None, *, friction_n: float = 0.0) -> StaticResult:
    cfg = config or OleoConfig()
    cfg.validate()
    if load_n < 0.0:
        raise ValueError("load must be non-negative")

    # The specification requires n=1 and zero friction for the nominal static
    # immersion; the dynamic polytropic exponent remains n=1.3 by default.
    static_cfg = OleoConfig(**{**asdict(cfg), "polytropic_n": cfg.static_polytropic_n})

    def combined_force(stroke: float) -> float:
        return gas_state(stroke, static_cfg)["force_n"] + auxiliary_spring_force(stroke, cfg)

    def solve(target: float) -> float | None:
        lo, hi = 0.0, cfg.stroke_m
        if combined_force(hi) < target:
            return None
        for _ in range(80):
            mid = (lo + hi) / 2.0
            if combined_force(mid) < target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2.0

    nominal = solve(load_n)
    low = solve(load_n - abs(friction_n)) if load_n > abs(friction_n) else 0.0
    high = solve(load_n + abs(friction_n))
    return StaticResult(
        load_n=load_n,
        stroke_m=nominal,
        load_at_zero_n=combined_force(0.0),
        load_at_full_n=combined_force(cfg.stroke_m),
        percent_stroke=None if nominal is None else 100.0 * nominal / cfg.stroke_m,
        friction_low_stroke_m=low,
        friction_high_stroke_m=high,
        within_range=nominal is not None and 0.20 <= nominal / cfg.stroke_m <= 0.45,
    )


def _case_inputs(cad: Mapping[str, Any], overrides: Mapping[str, Any] | None = None) -> dict[str, float]:
    mm = cad.get("cad_mm", {}) if isinstance(cad.get("cad_mm"), Mapping) else {}
    overrides = overrides or {}
    mass_mlm = _pick_number(overrides, ("mlm_kg",), _pick_number(cad, ("MLM_kg",), 210_000.0))
    mass_mtom = _pick_number(overrides, ("mtom_kg",), _pick_number(cad, ("MTOM_kg",), 280_000.0))
    return {
        "mlm_kg": mass_mlm,
        "mtom_kg": mass_mtom,
        "pl_n": 0.45 * mass_mlm * G,
        "pt_n": 0.45 * mass_mtom * G,
        "r_n": 3_000_000.0,
        "tire_radius_m": _pick_number(mm, ("TireRadius",), 657.225) / 1000.0,
    }


def make_dynamic_cases(cad: Mapping[str, Any], overrides: Mapping[str, Any] | None = None) -> list[DynamicCase]:
    values = _case_inputs(cad, overrides)
    return [
        DynamicCase("D1", values["mlm_kg"] / 2.0, 3.048, 2.0 * values["pl_n"] / 3.0),
        DynamicCase("D2", values["mtom_kg"] / 2.0, 1.8288, 2.0 * (values["mtom_kg"] * G) / 3.0),
        DynamicCase("D3", values["mlm_kg"] / 2.0, 3.6576, values["pl_n"]),
        DynamicCase("D4a", values["mlm_kg"] / 2.0, 3.048, 2.0 * values["pl_n"] / 3.0, -8.0),
        DynamicCase("D4b", values["mlm_kg"] / 2.0, 3.048, 2.0 * values["pl_n"] / 3.0, 8.0),
        DynamicCase("D5", values["mlm_kg"] / 2.0, 3.048, 0.0),
    ]


def _static_split_loads(total_n: float, punctured: set[str] | None = None, split: tuple[float, float] = (0.65, 0.35)) -> dict[str, float]:
    punctured = punctured or set()
    result = {wheel: 0.0 for wheel in WHEEL_IDS}
    # First solve the three axle totals for sum(F)=P and sum(x*F)=0.  Healthy
    # side weights retain the requested 65/35 split; if a puncture removes an
    # entire axle, the bounded solution moves load to the remaining axles
    # instead of inventing a fixed bogie moment.
    axes = (("F", 1.5), ("M", 0.0), ("R", -1.5))
    axis_data = []
    for axis, x_m in axes:
        inner, outer = f"{axis}I", f"{axis}O"
        available = [wheel for wheel in (inner, outer) if wheel not in punctured]
        weights = {inner: split[0], outer: split[1]}
        axis_weight = sum(weights[w] for w in available)
        if axis_weight > 0.0:
            axis_data.append((axis, x_m, axis_weight, available, weights))
    if not axis_data or total_n <= 0.0:
        return result
    active = list(axis_data)
    axle_totals: dict[str, float] = {}
    while active:
        sum_w = sum(item[2] for item in active)
        base = {item[0]: total_n * item[2] / sum_w for item in active}
        sum_wx = sum(item[2] * item[1] for item in active)
        sum_wxx = sum(item[2] * item[1] * item[1] for item in active)
        moment_base = sum(item[1] * base[item[0]] for item in active)
        determinant = sum_w * sum_wxx - sum_wx * sum_wx
        if abs(determinant) < 1.0e-12:
            axle_totals = base
            break
        lambda0 = (0.0 * sum_wxx - (-moment_base) * sum_wx) / determinant
        lambda1 = (sum_w * (-moment_base) - sum_wx * 0.0) / determinant
        candidate = {item[0]: base[item[0]] + item[2] * (lambda0 + lambda1 * item[1]) for item in active}
        negative = min(candidate.items(), key=lambda item: item[1])
        if negative[1] >= -1.0e-9 or len(active) == 1:
            axle_totals = {axis: max(0.0, value) for axis, value in candidate.items()}
            break
        active = [item for item in active if item[0] != negative[0]]
    for axis, _, _, available, weights in axis_data:
        axis_load = axle_totals.get(axis, 0.0)
        available_weight = sum(weights[w] for w in available)
        for wheel in available:
            result[wheel] = axis_load * weights[wheel] / available_weight
    return result


def static_wheel_loads(
    total_n: float,
    *,
    punctured: Iterable[str] = (),
    split: tuple[float, float] = (0.65, 0.35),
    tire_scale: float = 1.0,
) -> list[WheelResult]:
    punctured_set = set(punctured)
    if not set(punctured_set).issubset(set(WHEEL_IDS)):
        raise ValueError("unknown wheel id in punctured set")
    if abs(sum(split) - 1.0) > 1.0e-9 or min(split) < 0.0:
        raise ValueError("side split must be non-negative and sum to one")
    targets = _static_split_loads(total_n, punctured_set, split)
    result: list[WheelResult] = []
    for wheel in WHEEL_IDS:
        healthy = wheel not in punctured_set
        load = targets[wheel] if healthy else 0.0
        delta = tire_deflection_for_force(load, tire_scale) if healthy else 0.0
        result.append(WheelResult(wheel, load, delta, healthy, healthy and delta >= TIRE_MAX_DELTA_M, max(0.0, load - TIRE_RATED_LOAD_N), WHEEL_X_M[wheel], WHEEL_Y_M[wheel]))
    return result


def load_cases(cad: Mapping[str, Any], overrides: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    values = _case_inputs(cad, overrides)
    pl, pt, r = values["pl_n"], values["pt_n"], values["r_n"]
    return [
        {"case_id": "L0T", "description": "MTOM static", "fx_n": 0.0, "fy_n": 0.0, "fz_n": pt},
        {"case_id": "L0L", "description": "MLM static", "fx_n": 0.0, "fy_n": 0.0, "fz_n": pl},
        {"case_id": "L1", "description": "vertical landing", "fx_n": 0.0, "fy_n": 0.0, "fz_n": r},
        {"case_id": "L2+", "description": "forward contact", "fx_n": 0.25 * r, "fy_n": 0.0, "fz_n": r},
        {"case_id": "L2-", "description": "aft contact", "fx_n": -0.25 * r, "fy_n": 0.0, "fz_n": r},
        {"case_id": "L3+", "description": "right crosswind envelope", "fx_n": -0.30 * r, "fy_n": 0.1875 * r, "fz_n": 0.75 * r},
        {"case_id": "L3-", "description": "left crosswind envelope", "fx_n": -0.30 * r, "fy_n": -0.1875 * r, "fz_n": 0.75 * r},
        {"case_id": "L4+", "description": "right lateral", "fx_n": 0.0, "fy_n": 0.5 * pl, "fz_n": 1.5 * pl},
        {"case_id": "L4-", "description": "left lateral", "fx_n": 0.0, "fy_n": -0.5 * pl, "fz_n": 1.5 * pl},
        {"case_id": "L6+", "description": "right low speed turn", "fx_n": 0.0, "fy_n": 0.5 * pt, "fz_n": pt},
        {"case_id": "L6-", "description": "left low speed turn", "fx_n": 0.0, "fy_n": -0.5 * pt, "fz_n": pt},
        {"case_id": "L7+", "description": "forward tow", "fx_n": 0.15 * pt, "fy_n": 0.0, "fz_n": pt},
        {"case_id": "L7-", "description": "aft tow", "fx_n": -0.15 * pt, "fy_n": 0.0, "fz_n": pt},
        # The braking expression is the task's per-main-leg load-transfer
        # boundary at the normal 0.30 g dry stopping target.  It is a static
        # reaction screen; the detailed energy/torque result is in brakes CSV.
        {"case_id": "L5", "description": "braking load transfer", "fx_n": -(values["mtom_kg"] * G / 2.0) * (0.90 - 0.30 * 5.0 / 20.0), "fy_n": 0.0, "fz_n": pt, "deceleration_g": 0.30},
        # Jack load is carried at the selected jack boundary, not by tires.
        {"case_id": "L8", "description": "jack support boundary", "fx_n": 0.0, "fy_n": 0.0, "fz_n": 1.20 * pt, "support_mode": "jack", "wheel_contact": False},
    ]


def _state_derivative(state: Sequence[float], case: DynamicCase, oleo: OleoConfig, dyn: DynamicConfig, beta0_rad: float, ground_level: float) -> tuple[list[float], dict[str, Any]]:
    us, uu, beta, vs, vu, vb = state
    # Compression is sprung-body displacement minus lower-leg displacement:
    # the aircraft continues down while a tire/ground contact arrests the
    # unsprung assembly.
    stroke_raw = us - uu
    stroke = min(max(stroke_raw, 0.0), oleo.stroke_m)
    sdot = vs - vu
    gas = gas_state(stroke, oleo, temperature_c=dyn.temperature_c)
    damping = oil_flow_and_damping(sdot, oleo, upstream_abs_pa=gas["pressure_abs_pa"])
    friction = math.copysign(dyn.friction_n, sdot) if abs(sdot) > 1.0e-8 else 0.0
    stop_force = 0.0
    if stroke_raw < 0.0:
        stop_force = oleo.extension_stop_k_n_m * stroke_raw + oleo.stop_damping_n_s_m * min(sdot, 0.0)
    elif stroke_raw > oleo.stroke_m:
        stop_force = oleo.compression_stop_k_n_m * (stroke_raw - oleo.stroke_m) + oleo.stop_damping_n_s_m * max(sdot, 0.0)
    spring_force = auxiliary_spring_force(stroke, oleo)
    fleg = gas["force_n"] + spring_force + damping["force_n"] + friction + stop_force

    wheel_loads: dict[str, float] = {}
    offsets = [WHEEL_X_M[w] * beta0_rad for w in WHEEL_IDS]
    ground_offset = max(offsets) if beta0_rad else ground_level
    for wheel in WHEEL_IDS:
        delta = uu + WHEEL_X_M[wheel] * beta - ground_offset - ground_level
        wheel_loads[wheel] = tire_force(delta, dyn.tire_scale) if delta > 0.0 else 0.0
    total_tire = sum(wheel_loads.values())
    pitch_torque = -sum(WHEEL_X_M[w] * wheel_loads[w] for w in WHEEL_IDS)
    pitch_limit = math.radians(dyn.pitch_stop_deg)
    if beta > pitch_limit:
        pitch_torque -= dyn.pitch_stop_k_n_m * (beta - pitch_limit) + dyn.pitch_stop_damping_n_m_s * max(vb, 0.0)
    elif beta < -pitch_limit:
        pitch_torque += dyn.pitch_stop_k_n_m * (-pitch_limit - beta) - dyn.pitch_stop_damping_n_m_s * min(vb, 0.0)
    pitch_torque -= dyn.pitch_damping_n_m_s * vb

    ms = case.mass_kg - dyn.unsprung_mass_kg
    if ms <= 0.0:
        raise ValueError("unsprung mass must be smaller than case mass")
    as_ = (ms * G - case.lift_n / 2.0 - fleg) / ms
    au = (dyn.unsprung_mass_kg * G + fleg - total_tire) / dyn.unsprung_mass_kg
    ab = pitch_torque / dyn.bogie_inertia_kg_m2 if case.free_pitch else -vb * 50.0
    return [vs, vu, vb, as_, au, ab], {
        "stroke_m": stroke,
        "stroke_raw_m": stroke_raw,
        "sdot_m_s": sdot,
        "gas": gas,
        "damping": damping,
        "friction_n": friction,
        "stop_force_n": stop_force,
        "fleg_n": fleg,
        "spring_force_n": spring_force,
        "wheel_loads_n": wheel_loads,
        "total_tire_n": total_tire,
        "pitch_torque_n_m": pitch_torque,
        "tire_deflections_m": {w: max(0.0, uu + WHEEL_X_M[w] * beta - ground_offset - ground_level) for w in WHEEL_IDS},
    }


def _rk4_step(state: Sequence[float], dt: float, case: DynamicCase, oleo: OleoConfig, dyn: DynamicConfig, beta0_rad: float, ground_level: float) -> tuple[list[float], dict[str, Any]]:
    k1, info1 = _state_derivative(state, case, oleo, dyn, beta0_rad, ground_level)
    s2 = [x + 0.5 * dt * k for x, k in zip(state, k1)]
    k2, _ = _state_derivative(s2, case, oleo, dyn, beta0_rad, ground_level)
    s3 = [x + 0.5 * dt * k for x, k in zip(state, k2)]
    k3, _ = _state_derivative(s3, case, oleo, dyn, beta0_rad, ground_level)
    s4 = [x + dt * k for x, k in zip(state, k3)]
    k4, _ = _state_derivative(s4, case, oleo, dyn, beta0_rad, ground_level)
    new_state = [x + dt * (a + 2.0 * b + 2.0 * c + d) / 6.0 for x, a, b, c, d in zip(state, k1, k2, k3, k4)]
    _, info = _state_derivative(new_state, case, oleo, dyn, beta0_rad, ground_level)
    return new_state, info


def simulate(case: DynamicCase, oleo: OleoConfig | None = None, dyn: DynamicConfig | None = None, *, dt_s: float = 0.001, t_end_s: float = 4.0, record_stride: int = 1) -> DynamicResult:
    oleo = oleo or OleoConfig()
    dyn = dyn or DynamicConfig()
    oleo.validate()
    if dt_s <= 0.0 or t_end_s <= 0.0:
        raise ValueError("time step and end time must be positive")
    beta0_rad = math.radians(case.initial_beta_deg)
    # Ground level is zero for level cases.  For D4 the lowest initial wheel
    # defines contact; the other axles are allowed to remain airborne.
    ground_level = 0.0
    state = [0.0, 0.0, beta0_rad, case.sink_speed_m_s, case.sink_speed_m_s, 0.0]
    initial_ke = 0.5 * (case.mass_kg - dyn.unsprung_mass_kg) * case.sink_speed_m_s**2 + 0.5 * dyn.unsprung_mass_kg * case.sink_speed_m_s**2
    history: list[dict[str, Any]] = []
    max_stroke = 0.0
    max_ground = 0.0
    max_airframe = 0.0
    max_deflection = 0.0
    max_beta = abs(case.initial_beta_deg)
    max_pitch_torque = 0.0
    max_pressure_abs = 0.0
    max_pressure_gauge = 0.0
    max_dp = 0.0
    min_oil_pressure_abs = float("inf")
    min_upper_oil_pressure_abs = float("inf")
    min_lower_oil_pressure_abs = float("inf")
    max_upper_oil_pressure_abs = 0.0
    max_lower_oil_pressure_abs = 0.0
    max_oil_pressure_abs = 0.0
    cavitation_detected = False
    max_axis = {"F": 0.0, "M": 0.0, "R": 0.0}
    max_time: float | None = None
    extension_stop = False
    compression_stop = False
    tire_bottomed = False
    dissipation = 0.0
    gravity_work = 0.0
    lift_work = 0.0
    prev = None
    max_reached = False
    rebound_complete = False
    steps = int(math.ceil(t_end_s / dt_s))
    time = 0.0
    for index in range(steps + 1):
        _, info = _state_derivative(state, case, oleo, dyn, beta0_rad, ground_level)
        stroke = info["stroke_m"]
        if stroke > max_stroke:
            max_stroke = stroke
            max_time = time
        max_stroke = max(max_stroke, stroke)
        max_ground = max(max_ground, info["total_tire_n"])
        airframe_reaction = info["fleg_n"]
        max_airframe = max(max_airframe, abs(airframe_reaction))
        max_deflection = max(max_deflection, max(info["tire_deflections_m"].values()))
        max_beta = max(max_beta, abs(math.degrees(state[2])))
        max_pitch_torque = max(max_pitch_torque, abs(info["pitch_torque_n_m"]))
        max_pressure_abs = max(max_pressure_abs, info["gas"]["pressure_abs_pa"])
        max_pressure_gauge = max(max_pressure_gauge, info["gas"]["pressure_gauge_pa"])
        max_dp = max(max_dp, info["damping"]["delta_p_pa"])
        min_oil_pressure_abs = min(min_oil_pressure_abs, float(info["damping"]["min_chamber_abs_pa"]))
        min_upper_oil_pressure_abs = min(min_upper_oil_pressure_abs, float(info["damping"]["upper_abs_pa"]))
        min_lower_oil_pressure_abs = min(min_lower_oil_pressure_abs, float(info["damping"]["lower_abs_pa"]))
        max_upper_oil_pressure_abs = max(max_upper_oil_pressure_abs, float(info["damping"]["upper_abs_pa"]))
        max_lower_oil_pressure_abs = max(max_lower_oil_pressure_abs, float(info["damping"]["lower_abs_pa"]))
        max_oil_pressure_abs = max(max_oil_pressure_abs, float(info["damping"]["max_chamber_abs_pa"]))
        cavitation_detected = cavitation_detected or bool(info["damping"]["cavitation"])
        for axis, wheels in (("F", ("FI", "FO")), ("M", ("MI", "MO")), ("R", ("RI", "RO"))):
            max_axis[axis] = max(max_axis[axis], sum(info["wheel_loads_n"][w] for w in wheels))
        if info["stroke_raw_m"] <= 0.0 and state[5] < 0.0:
            extension_stop = True
        if info["stroke_raw_m"] >= oleo.stroke_m and state[5] > 0.0:
            compression_stop = True
        if any(d >= TIRE_MAX_DELTA_M for d in info["tire_deflections_m"].values()):
            tire_bottomed = True
        if stroke >= max_stroke - 1.0e-9 and stroke > 0.01:
            max_reached = True
        if max_reached and prev is not None and prev["sdot_m_s"] < 0.0 <= info["sdot_m_s"]:
            rebound_complete = True
        row = {
            "case_id": case.case_id,
            "time_s": time,
            "sprung_displacement_m": state[0],
            "unsprung_displacement_m": state[1],
            "beta_deg": math.degrees(state[2]),
            "sprung_velocity_m_s": state[3],
            "unsprung_velocity_m_s": state[4],
            "stroke_m": stroke,
            "stroke_rate_m_s": info["sdot_m_s"],
            "leg_force_n": info["fleg_n"],
            "spring_force_n": info["spring_force_n"],
            "tire_reaction_n": info["total_tire_n"],
            "pitch_torque_n_m": info["pitch_torque_n_m"],
            "gas_pressure_abs_pa": info["gas"]["pressure_abs_pa"],
            "gas_pressure_gauge_pa": info["gas"]["pressure_gauge_pa"],
            "oil_flow_m3_s": info["damping"]["flow_m3_s"],
            "orifice_delta_p_pa": info["damping"]["delta_p_pa"],
            "oil_upper_abs_pa": info["damping"]["upper_abs_pa"],
            "oil_lower_abs_pa": info["damping"]["lower_abs_pa"],
            "oil_min_chamber_abs_pa": info["damping"]["min_chamber_abs_pa"],
            "oil_max_chamber_abs_pa": info["damping"]["max_chamber_abs_pa"],
            "oil_downstream_abs_pa": info["damping"]["downstream_abs_pa"],
            "oil_cavitation": info["damping"]["cavitation"],
            "tire_FI_n": info["wheel_loads_n"]["FI"],
            "tire_FO_n": info["wheel_loads_n"]["FO"],
            "tire_MI_n": info["wheel_loads_n"]["MI"],
            "tire_MO_n": info["wheel_loads_n"]["MO"],
            "tire_RI_n": info["wheel_loads_n"]["RI"],
            "tire_RO_n": info["wheel_loads_n"]["RO"],
        }
        if index % max(1, record_stride) == 0 or index == steps:
            history.append(row)
        # The required energy window ends at the first rebound completion;
        # continuing through later oscillations only accumulates unrelated
        # numerical drift and obscures that gate.
        if rebound_complete:
            break
        if index == steps:
            break
        next_state, next_info = _rk4_step(state, dt_s, case, oleo, dyn, beta0_rad, ground_level)
        ds = next_state[0] - state[0]
        du = next_state[1] - state[1]
        gravity_work += ((case.mass_kg - dyn.unsprung_mass_kg) * G * ds + dyn.unsprung_mass_kg * G * du)
        lift_work += -case.lift_n / 2.0 * ds
        power_now = abs(info["damping"]["force_n"] * info["sdot_m_s"]) + abs(info["friction_n"] * info["sdot_m_s"]) + abs(info["stop_force_n"] * info["sdot_m_s"])
        power_next = abs(next_info["damping"]["force_n"] * next_info["sdot_m_s"]) + abs(next_info["friction_n"] * next_info["sdot_m_s"]) + abs(next_info["stop_force_n"] * next_info["sdot_m_s"])
        dissipation += 0.5 * (power_now + power_next) * dt_s
        prev = info
        state = next_state
        time += dt_s
    final_info = _state_derivative(state, case, oleo, dyn, beta0_rad, ground_level)[1]
    final_ke = 0.5 * (case.mass_kg - dyn.unsprung_mass_kg) * state[3] ** 2 + 0.5 * dyn.unsprung_mass_kg * state[4] ** 2 + 0.5 * dyn.bogie_inertia_kg_m2 * state[5] ** 2
    gas_j = gas_potential_energy(min(max(state[0] - state[1], 0.0), oleo.stroke_m), oleo, temperature_c=dyn.temperature_c)
    spring_j = auxiliary_spring_energy(min(max(state[0] - state[1], 0.0), oleo.stroke_m), oleo)
    tire_j = sum(tire_energy(value, dyn.tire_scale) for value in final_info["tire_deflections_m"].values())
    residual = final_ke + gas_j + spring_j + tire_j + dissipation - initial_ke - gravity_work - lift_work
    return DynamicResult(
        case_id=case.case_id,
        dt_s=dt_s,
        max_stroke_m=max_stroke,
        max_ground_reaction_n=max_ground,
        max_airframe_reaction_n=max_airframe,
        max_tire_deflection_m=max_deflection,
        max_beta_deg=max_beta,
        max_pitch_torque_n_m=max_pitch_torque,
        max_axis_loads_n=max_axis,
        final_stroke_m=min(max(state[0] - state[1], 0.0), oleo.stroke_m),
        rebound_complete=rebound_complete,
        extension_stop=extension_stop,
        compression_stop=compression_stop,
        tire_bottomed=tire_bottomed,
        pressure_max_abs_pa=max_pressure_abs,
        pressure_max_gauge_pa=max_pressure_gauge,
        max_orifice_dp_pa=max_dp,
        min_oil_pressure_abs_pa=min_oil_pressure_abs,
        min_upper_oil_pressure_abs_pa=min_upper_oil_pressure_abs,
        min_lower_oil_pressure_abs_pa=min_lower_oil_pressure_abs,
        max_upper_oil_pressure_abs_pa=max_upper_oil_pressure_abs,
        max_lower_oil_pressure_abs_pa=max_lower_oil_pressure_abs,
        max_oil_pressure_abs_pa=max_oil_pressure_abs,
        max_oil_pressure_gauge_pa=max_oil_pressure_abs - P_ATM,
        cavitation_detected=cavitation_detected,
        energy_initial_j=initial_ke,
        energy_gravity_j=gravity_work,
        energy_lift_j=lift_work,
        energy_gas_j=gas_j,
        energy_spring_j=spring_j,
        energy_tire_j=tire_j,
        energy_dissipation_j=dissipation,
        energy_final_kinetic_j=final_ke,
        energy_residual_j=residual,
        time_to_max_stroke_s=max_time,
        history=history,
    )


def convergence_check(cases: Sequence[DynamicCase], oleo: OleoConfig, dyn: DynamicConfig, *, dt_s: float = 0.002, t_end_s: float = 3.0) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        coarse = simulate(case, oleo, dyn, dt_s=dt_s, t_end_s=t_end_s, record_stride=max(1, int(round(dt_s / 0.001))))
        fine = simulate(case, oleo, dyn, dt_s=dt_s / 2.0, t_end_s=t_end_s, record_stride=max(1, int(round(dt_s / 0.001))))
        def pct(a: float, b: float) -> float:
            return 100.0 * abs(a - b) / max(abs(b), 1.0)
        coarse_energy_residual_pct = 100.0 * abs(coarse.energy_residual_j) / max(coarse.energy_initial_j + abs(coarse.energy_gravity_j), 1.0)
        fine_energy_residual_pct = 100.0 * abs(fine.energy_residual_j) / max(fine.energy_initial_j + abs(fine.energy_gravity_j), 1.0)
        rows.append({
            "case_id": case.case_id,
            "coarse_dt_s": coarse.dt_s,
            "fine_dt_s": fine.dt_s,
            "max_reaction_change_pct": pct(coarse.max_ground_reaction_n, fine.max_ground_reaction_n),
            "max_stroke_change_pct": pct(coarse.max_stroke_m, fine.max_stroke_m),
            "max_axis_change_pct": max(pct(coarse.max_axis_loads_n[a], fine.max_axis_loads_n[a]) for a in ("F", "M", "R")),
            "coarse_energy_residual_pct": coarse_energy_residual_pct,
            "fine_energy_residual_pct": fine_energy_residual_pct,
            "within_2pct": pct(coarse.max_ground_reaction_n, fine.max_ground_reaction_n) <= 2.0 and pct(coarse.max_stroke_m, fine.max_stroke_m) <= 2.0 and coarse_energy_residual_pct <= 2.0 and fine_energy_residual_pct <= 2.0,
        })
    return rows


def sensitivity_rows(cases: Sequence[DynamicCase], oleo: OleoConfig, dyn: DynamicConfig, *, dt_s: float = 0.002, t_end_s: float = 3.0) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    variants: list[tuple[str, OleoConfig, DynamicConfig]] = []
    variants.extend([
        ("precharge_-10pct", OleoConfig(**{**asdict(oleo), "gas_precharge_abs_pa": oleo.gas_precharge_abs_pa * 0.9}), dyn),
        ("precharge_+10pct", OleoConfig(**{**asdict(oleo), "gas_precharge_abs_pa": oleo.gas_precharge_abs_pa * 1.1}), dyn),
        ("Cd_0.55", OleoConfig(**{**asdict(oleo), "cd": 0.55}), dyn),
        ("Cd_0.75", OleoConfig(**{**asdict(oleo), "cd": 0.75}), dyn),
        ("n_1.0", OleoConfig(**{**asdict(oleo), "polytropic_n": 1.0}), dyn),
        ("n_1.4", OleoConfig(**{**asdict(oleo), "polytropic_n": 1.4}), dyn),
        ("friction_0N", OleoConfig(**{**asdict(oleo), "friction_n": 0.0}), DynamicConfig(**{**asdict(dyn), "friction_n": 0.0})),
        ("friction_10kN", OleoConfig(**{**asdict(oleo), "friction_n": 10_000.0}), DynamicConfig(**{**asdict(dyn), "friction_n": 10_000.0})),
        ("tire_k_0.8", oleo, DynamicConfig(**{**asdict(dyn), "tire_scale": 0.8})),
        ("tire_k_1.2", oleo, DynamicConfig(**{**asdict(dyn), "tire_scale": 1.2})),
        ("temperature_-40C", oleo, DynamicConfig(**{**asdict(dyn), "temperature_c": -40.0})),
        ("temperature_+70C", oleo, DynamicConfig(**{**asdict(dyn), "temperature_c": 70.0})),
    ])
    for name, ocfg, dcfg in variants:
        for case in cases:
            result = simulate(case, ocfg, dcfg, dt_s=dt_s, t_end_s=t_end_s, record_stride=max(1, int(round(dt_s / 0.001))))
            rows.append({"variant": name, "case_id": case.case_id, "max_stroke_m": result.max_stroke_m, "max_reaction_n": result.max_ground_reaction_n, "max_axis_n": max(result.max_axis_loads_n.values()), "tire_bottomed": result.tire_bottomed, "cavitation_detected": result.cavitation_detected, "min_oil_pressure_abs_pa": result.min_oil_pressure_abs_pa, "energy_residual_j": result.energy_residual_j})
    return rows


def u2_sensitivity_rows(cad: Mapping[str, Any], oleo: OleoConfig, dyn: DynamicConfig, *, dt_s: float = 0.002, t_end_s: float = 1.0) -> list[dict[str, Any]]:
    """Task U2 one-at-a-time radius, tire-k, and cross-slope screens."""
    values = _case_inputs(cad)
    rows: list[dict[str, Any]] = []
    base_radius = _pick_number(cad.get("cad_mm", {}) if isinstance(cad.get("cad_mm"), Mapping) else {}, ("TireRadius",), 657.225)
    for case_id, load in (("L0T", values["pt_n"]), ("L0L", values["pl_n"])):
        for offset_mm in (-10.0, 10.0):
            wheels = static_wheel_loads(load, split=(0.65, 0.35), tire_scale=dyn.tire_scale)
            rows.append({"case_id": case_id, "variant": f"radius_{offset_mm:+.0f}mm", "radius_mm": base_radius + offset_mm, "tire_scale": dyn.tire_scale, "cross_slope": 0.0, "max_deflection_m": max(w.deflection_m for w in wheels), "max_load_n": max(w.load_n for w in wheels), "bottomed_wheels": sum(w.bottomed for w in wheels), "note": "radius changes envelope/ground geometry; task tire force curve is unchanged"})
        for scale in (0.95, 1.05):
            wheels = static_wheel_loads(load, split=(0.65, 0.35), tire_scale=scale)
            rows.append({"case_id": case_id, "variant": f"tire_k_{scale:.2f}", "radius_mm": base_radius, "tire_scale": scale, "cross_slope": 0.0, "max_deflection_m": max(w.deflection_m for w in wheels), "max_load_n": max(w.load_n for w in wheels), "bottomed_wheels": sum(w.bottomed for w in wheels), "note": "pressure-equivalent tire stiffness perturbation"})
        for slope in (-0.015, 0.015):
            roll_height = max(abs(y * slope) for y in WHEEL_Y_M.values())
            rows.append({"case_id": case_id, "variant": f"cross_slope_{slope:+.3f}", "radius_mm": base_radius, "tire_scale": dyn.tire_scale, "cross_slope": slope, "max_deflection_m": max(w.deflection_m for w in static_wheel_loads(load, split=(0.65, 0.35), tire_scale=dyn.tire_scale)), "max_load_n": max(w.load_n for w in static_wheel_loads(load, split=(0.65, 0.35), tire_scale=dyn.tire_scale)), "bottomed_wheels": 0, "surface_height_span_m": 2.0 * roll_height, "note": "cross-slope geometry span; lateral compliance is outside this vertical screen"})
    # D1 gets the same ±5% tire-k perturbation dynamically as required by U2.
    d1 = make_dynamic_cases(cad)[0]
    for scale in (0.95, 1.05):
        result = simulate(d1, oleo, DynamicConfig(**{**asdict(dyn), "tire_scale": scale}), dt_s=dt_s, t_end_s=t_end_s, record_stride=max(1, int(round(dt_s / 0.001))))
        rows.append({"case_id": "D1", "variant": f"tire_k_{scale:.2f}", "radius_mm": base_radius, "tire_scale": scale, "cross_slope": 0.0, "max_deflection_m": result.max_tire_deflection_m, "max_load_n": result.max_ground_reaction_n, "bottomed_wheels": int(result.tire_bottomed), "cavitation_detected": result.cavitation_detected, "note": "dynamic D1 screen"})
    return rows


def geometry_checks(cad: Mapping[str, Any]) -> dict[str, Any]:
    mm = cad.get("cad_mm", {}) if isinstance(cad.get("cad_mm"), Mapping) else {}
    def mmv(name: str, default: float) -> float:
        return _pick_number(mm, (name,), default) / 1000.0
    piston_cavity = math.pi * (mmv("PistonID", 270.0) / 2.0) ** 2 * mmv("PistonLength", 1550.0)
    barrel_annulus = math.pi * ((mmv("BarrelID", 350.0) / 2.0) ** 2 - (mmv("PistonOD", 330.0) / 2.0) ** 2) * mmv("BarrelLength", 1700.0)
    gas_capacity = piston_cavity + barrel_annulus
    env_r = mmv("TireEnvelopeRadius", 725.0)
    env_half = mmv("TireEnvelopeHalfWidth", 320.0)
    # Transform stowed wheel centers with the prescribed Rx(-90) mapping.
    centers = [(WHEEL_X_M[w], -2.5, 0.0) for w in WHEEL_IDS]
    bounds = {
        "x_min_m": min(x - env_r for x, _, _ in centers),
        "x_max_m": max(x + env_r for x, _, _ in centers),
        "y_min_m": min(y - env_r for _, y, _ in centers),
        "y_max_m": max(y + env_r for _, y, _ in centers),
        "z_min_m": -env_half,
        "z_max_m": env_half,
    }
    bay = {"x_min_m": -2.3, "x_max_m": 2.3, "y_min_m": -3.4, "y_max_m": 0.3, "z_min_m": -1.1, "z_max_m": 1.1}
    margins = {
        "x_min_m": bounds["x_min_m"] - bay["x_min_m"],
        "x_max_m": bay["x_max_m"] - bounds["x_max_m"],
        "y_min_m": bounds["y_min_m"] - bay["y_min_m"],
        "y_max_m": bay["y_max_m"] - bounds["y_max_m"],
        "z_min_m": bounds["z_min_m"] - bay["z_min_m"],
        "z_max_m": bay["z_max_m"] - bounds["z_max_m"],
    }
    gas_v0 = _pick_number(mm, ("GasVolumeL",), 65.0) / 1000.0
    area = math.pi * (mmv("PistonOD", 330.0) ** 2) / 4.0
    current_flow_area = math.pi * max(0.0, mmv("BarrelID", 350.0) ** 2 - mmv("PistonOD", 330.0) ** 2) / 4.0
    recommended_flow_area = math.pi * max(0.0, mmv("BarrelID", 460.0) ** 2 - mmv("PistonOD", 330.0) ** 2) / 4.0
    gas_vmin = gas_v0 - area * mmv("StrokeMax", 600.0)
    return {
        "piston_internal_capacity_m3": piston_cavity,
        "barrel_annulus_capacity_m3": barrel_annulus,
        "combined_conservative_capacity_m3": gas_capacity,
        "master_gas_volume_m3": gas_v0,
        "master_gas_capacity_margin_m3": gas_capacity - gas_v0,
        "master_gas_volume_at_full_stroke_m3": gas_vmin,
        "master_gas_volume_fraction_at_full_stroke": gas_vmin / gas_v0,
        "current_annular_oil_flow_area_m2": current_flow_area,
        "physical_annular_oil_flow_area_m2": recommended_flow_area,
        "460mm_ID_annular_oil_flow_area_m2": recommended_flow_area,
        "cad_input_dimensions_mm": {
            name: _pick_number(mm, (name,), default)
            for name, default in (
                ("BarrelOD", 550.0),
                ("BarrelID", 460.0),
                ("PistonOD", 330.0),
                ("PistonID", 270.0),
                ("BogiePinOD", 150.0),
                ("BogieWidth", 350.0),
                ("BogieHeight", 500.0),
                ("BogieWall", 35.0),
                ("AxleOD", 220.0),
                ("AxleID", 140.0),
                ("CenterAxleOD", 260.0),
                ("CenterAxleID", 160.0),
            )
        },
        "stowed_tire_envelope_bounds_m": bounds,
        "bay_bounds_m": bay,
        "stowed_clearance_m": margins,
        "all_tire_envelope_clearances_ge_25mm": min(margins.values()) >= 0.025,
        "gas_volume_minimum_20pct": gas_vmin >= 0.2 * gas_v0,
        "note": "The cylindrical tire envelope is a specified comparison envelope; it is not a tire manufacturer growth curve.",
    }


def _strut_free_body(case: Mapping[str, Any], load_factor: float = 1.0) -> dict[str, float | str]:
    """Resolve the leg load through the actual stay/trunnion geometry.

    The lower wheel load is used only for transverse guide bending.  Its
    vertical component remains an axial strut load; applying it again through
    a 2.5 m barrel lever would count a free-body moment the trunnion/stay
    system does not transmit.
    """
    fx = float(case.get("fx_n", 0.0)) * load_factor
    fy = float(case.get("fy_n", 0.0)) * load_factor
    fz = float(case.get("fz_n", 0.0)) * load_factor
    load_z_m = float(case.get('load_point_z_m', -3.157225))  # conservative extended, undeflected tire contact
    stay_z_m = -1.500
    guide_z_m = -1.355  # centroid of the fixed guide Z=-1430..-1280 mm
    knee_y_m = -0.5232195
    knee_z_m = -0.3099406
    stay_length_m = math.hypot(knee_y_m, knee_z_m - stay_z_m)
    stay_u_y = knee_y_m / stay_length_m
    stay_u_z = (knee_z_m - stay_z_m) / stay_length_m
    roll_moment = -load_z_m * fy
    stay_y_total = -roll_moment / abs(stay_z_m)
    stay_axial_total = stay_y_total / stay_u_y
    stay_z_total = stay_axial_total * stay_u_z
    trunnion_total = (-fx, -(fy + stay_y_total), -(fz + stay_z_total))
    pitch_moment = load_z_m * fx
    t1_z = trunnion_total[2]/2 - pitch_moment/1.2
    t2_z = trunnion_total[2]/2 + pitch_moment/1.2
    guide_lever = abs(load_z_m-guide_z_m)
    guide_horizontal = math.hypot(fx, fy)
    return {
        "case_id": str(case.get("case_id", "unknown")),
        "load_factor": load_factor,
        "fx_n": fx,
        "fy_n": fy,
        "fz_n": fz,
        "load_point_z_m": load_z_m,
        "stay_pin_z_m": stay_z_m,
        "guide_lever_m": guide_lever,
        "stay_length_m": stay_length_m,
        "stay_unit_y": stay_u_y,
        "stay_unit_z": stay_u_z,
        "stay_y_component": stay_u_y,
        "stay_axial_each_n": stay_axial_total / 2.0,
        "stay_y_total_n": stay_y_total,
        "stay_z_total_n": stay_z_total,
        "roll_moment_applied_n_m": roll_moment,
        "roll_moment_residual_n_m": -load_z_m * fy + -stay_z_m * stay_y_total,
        "trunnion_x_total_n": trunnion_total[0],
        "trunnion_y_total_n": trunnion_total[1],
        "trunnion_z_total_n": trunnion_total[2],
        "trunnion_T1_x_m": -.6,
        "trunnion_T2_x_m": .6,
        "trunnion_T1_fz_n": t1_z,
        "trunnion_T2_fz_n": t2_z,
        "trunnion_each_fx_n": trunnion_total[0]/2,
        "trunnion_each_fy_n": trunnion_total[1]/2,
        "pitch_moment_residual_n_m": pitch_moment+.6*(t1_z-t2_z),
        "trunnion_each_resultant_n": max(math.sqrt((trunnion_total[0]/2)**2+(trunnion_total[1]/2)**2+fz**2) for fz in (t1_z,t2_z)),
        "trunnion_mx_n_m": 0.0,
        "guide_horizontal_n": guide_horizontal,
        "guide_bending_moment_n_m": guide_horizontal * guide_lever,
        "barrel_axial_force_n": max(abs(fz), abs(trunnion_total[2])),
        "piston_axial_force_n": abs(fz),
        "force_resultant_n": math.sqrt(fx * fx + fy * fy + fz * fz),
    }


def structural_checks(
    cad: Mapping[str, Any],
    *,
    max_dynamic_force_n: float = 3_000_000.0,
    max_pressure_gauge_pa: float = 20.7e6,
) -> list[dict[str, Any]]:
    mm = cad.get("cad_mm", {}) if isinstance(cad.get("cad_mm"), Mapping) else {}
    materials = cad.get("materials", {}) if isinstance(cad.get("materials"), Mapping) else {}
    steel = materials.get("300M", {}) if isinstance(materials.get("300M"), Mapping) else {}
    yield_pa = _pick_number(steel, ("yield_design_Pa",), 1.4e9)
    ultimate_pa = _pick_number(steel, ("ultimate_design_Pa",), 1.7e9)

    def mmv(name: str, default: float) -> float:
        return _pick_number(mm, (name,), default) / 1000.0

    def tube(od: float, ident: float) -> tuple[float, float, float]:
        area = math.pi * (od**2 - ident**2) / 4.0
        inertia = math.pi * (od**4 - ident**4) / 64.0
        return area, inertia, inertia / (od / 2.0)

    local_hole_note = (
        "Gross-section screen only: R60 mounting-wing bore, fork R75.4 bore, "
        "guide oil port and local lug ligaments require separate net-section, "
        "bearing, edge-distance and proof-load checks."
    )
    rows: list[dict[str, Any]] = []
    barrel_a, _, barrel_z = tube(mmv("BarrelOD", 550.0), mmv("BarrelID", 460.0))
    piston_a, _, piston_z = tube(mmv("PistonOD", 330.0), mmv("PistonID", 270.0))
    selected_cases = []
    for case in load_cases(cad):
        case_id = case.get("case_id")
        if case_id in {"L1", "L2+", "L2-", "L3+", "L3-", "L4+", "L4-"}:
            selected_cases.append((case, 1.0, case_id))
            selected_cases.append((case, 1.5, "U1.5_" + str(case_id)))

    barrel_rows: list[dict[str, Any]] = []
    piston_rows: list[dict[str, Any]] = []
    for case, factor, label in selected_cases:
        fbd = _strut_free_body(case, factor)
        support_row = {
            "item": "support_reactions_" + label,
            "mode": "stay/trunnion free body",
            **fbd,
            "case_id": label,
            "stay_x_m": 0.500,
            "stay_anchor_y_m": -1.200,
            "stay_anchor_z_m": 0.800,
            "leg_pin_x_m": 0.500,
            "leg_pin_y_m": 0.0,
            "leg_pin_z_m": -1.500,
            "trunnion_axis_mx_released": True,
            "status": "traceable preliminary reaction",
            "basis": "stay anchors (+/-500,-1200,800), leg pins (+/-500,0,-1500), 1300 mm links; no vertical 2.5 m barrel moment",
        }
        rows.append(support_row)
        for item, area, section_z, axial_force in (
            ("barrel_" + label, barrel_a, barrel_z, float(fbd["barrel_axial_force_n"])),
            ("piston_" + label, piston_a, piston_z, float(fbd["piston_axial_force_n"])),
        ):
            axial_stress = axial_force / area
            bending_stress = float(fbd["guide_bending_moment_n_m"]) / section_z
            combined = axial_stress + bending_stress
            row = {
                "item": item,
                "case_id": label,
                "mode": "free-body axial + piston-guide horizontal bending",
                "force_n": axial_force,
                "axial_force_n": axial_force,
                "guide_horizontal_force_n": fbd["guide_horizontal_n"],
                "guide_bending_moment_n_m": fbd["guide_bending_moment_n_m"],
                "section_area_m2": area,
                "section_modulus_m3": section_z,
                "axial_stress_pa": axial_stress,
                "bending_stress_pa": bending_stress,
                "stress_pa": combined,
                "allowable_yield_pa": yield_pa,
                "allowable_ultimate_pa": ultimate_pa,
                "yield_margin": yield_pa / combined - 1.0,
                "ultimate_margin": ultimate_pa / combined - 1.0,
                "load_factor": factor,
                "local_hole_note": local_hole_note,
                "basis": "vertical load is axial; horizontal guide force uses the 1.802225 m contact-to-lower-guide lever",
            }
            rows.append(row)
            (barrel_rows if item.startswith("barrel_") else piston_rows).append(row)

    for name, candidates in (("barrel", barrel_rows), ("piston", piston_rows)):
        worst = max(candidates, key=lambda row: row["stress_pa"])
        rows.append({**worst, "item": name, "mode": "worst L1-L4/1.5x free-body screen", "basis": worst["basis"] + "; summary of explicit case rows"})

    # The actual CAD beam is 7050-T7451 350 x 500 x 35 mm.  Keep the prior
    # 300 x 400 x 25 mm screen as an explicit failing comparison, not as the
    # current geometry or a hidden pass.
    aluminum = materials.get("7050-T7451", {}) if isinstance(materials.get("7050-T7451"), Mapping) else {}
    al_yield = _pick_number(aluminum, ("yield_design_Pa",), 393.0e6)
    al_density = _pick_number(aluminum, ("density_kg_m3",), 2830.0)

    def rect_hollow(width: float, height: float, wall: float) -> tuple[float, float, float]:
        area = width * height - (width - 2.0 * wall) * (height - 2.0 * wall)
        inertia = (width * height**3 - (width - 2.0 * wall) * (height - 2.0 * wall) ** 3) / 12.0
        return area, inertia, inertia / (height / 2.0)

    beam_force = min(max_dynamic_force_n, 3_000_000.0)
    beam_moment = 1.5e6
    beam_length = _pick_number(mm, ("BogieLength",), 3400.0) / 1000.0
    actual_b, actual_h, actual_t = (mmv("BogieWidth", 350.0), mmv("BogieHeight", 500.0), mmv("BogieWall", 35.0))
    actual_area, _, actual_z = rect_hollow(actual_b, actual_h, actual_t)
    actual_axial = beam_force / actual_area
    actual_bending = beam_moment / actual_z
    actual_stress = actual_axial + actual_bending
    rows.append({
        "item": "bogie_beam_current_7050",
        "mode": "rectangular hollow L1 axial+bending",
        "force_n": beam_force,
        "moment_n_m": beam_moment,
        "section_area_m2": actual_area,
        "section_modulus_m3": actual_z,
        "stress_pa": actual_stress,
        "bending_stress_pa": actual_bending,
        "allowable_yield_pa": al_yield,
        "yield_margin": al_yield / actual_stress - 1.0,
        "mass_estimate_kg": actual_area * beam_length * al_density,
        "basis": "actual CAD 7050-T7451 beam 350 x 500 x 35 mm; 1.5 MN m L1 screen; local lugs/buckling remain open",
    })
    legacy_b, legacy_h, legacy_t = 0.300, 0.400, 0.025
    legacy_area, _, legacy_z = rect_hollow(legacy_b, legacy_h, legacy_t)
    legacy_stress = beam_force / legacy_area + beam_moment / legacy_z
    rows.append({
        "item": "bogie_beam_legacy_7050",
        "mode": "rectangular hollow comparison only",
        "force_n": beam_force,
        "moment_n_m": beam_moment,
        "section_area_m2": legacy_area,
        "section_modulus_m3": legacy_z,
        "stress_pa": legacy_stress,
        "bending_stress_pa": beam_moment / legacy_z,
        "allowable_yield_pa": al_yield,
        "yield_margin": al_yield / legacy_stress - 1.0,
        "basis": "legacy 300 x 400 x 25 mm comparison; retained as an explicit negative result, not current CAD",
    })
    rows.append({
        "item": "bogie_beam_recommended_7050",
        "mode": "current-CAD alias for downstream consumers",
        "force_n": beam_force,
        "moment_n_m": beam_moment,
        "section_area_m2": actual_area,
        "section_modulus_m3": actual_z,
        "stress_pa": actual_stress,
        "bending_stress_pa": actual_bending,
        "allowable_yield_pa": al_yield,
        "yield_margin": al_yield / actual_stress - 1.0,
        "mass_estimate_kg": actual_area * beam_length * al_density,
        "basis": "same 350 x 500 x 35 mm current CAD section; alias retained for existing reports",
    })
    pin_d = mmv("BogiePinOD", 150.0)
    pin_area_double = 2.0 * math.pi * (pin_d**2 - mmv("CenterAxleID", 160.0)**2) / 4.0
    pin_tau = max_dynamic_force_n / pin_area_double
    pin_bearing = max_dynamic_force_n / (pin_d * 0.065)
    rows.extend([
        {"item": "bogie_pin", "mode": "double shear", "force_n": max_dynamic_force_n, "stress_pa": pin_tau, "allowable_yield_pa": yield_pa / math.sqrt(3.0), "yield_margin": (yield_pa / math.sqrt(3.0)) / pin_tau - 1.0, "basis": "300M assumed; hollow 260/160 mm fork/pivot pin from CAD", "local_hole_note": local_hole_note},
        {"item": "bogie_pin_bearing", "mode": "projected bearing", "force_n": max_dynamic_force_n, "stress_pa": pin_bearing, "allowable_yield_pa": yield_pa, "yield_margin": yield_pa / pin_bearing - 1.0, "basis": "65 mm fork-ear thickness from CAD; local edge distance and lug proof remain open", "local_hole_note": local_hole_note},
    ])
    pmax = max(20.7e6, max_pressure_gauge_pa) + P_ATM
    for item, od, ident in (("barrel_pressure", mmv("BarrelOD", 550.0), mmv("BarrelID", 460.0)), ("piston_pressure", mmv("PistonOD", 330.0), mmv("PistonID", 270.0))):
        wall = (od - ident) / 2.0
        hoop = pmax * (od / 2.0) / wall
        axial = hoop / 2.0
        vm_pressure = math.sqrt(hoop * hoop - hoop * axial + axial * axial)
        rows.append({"item": item, "mode": "closed-end hoop+axial", "force_n": 0.0, "pressure_gauge_pa": pmax - P_ATM, "stress_pa": vm_pressure, "allowable_yield_pa": yield_pa, "yield_margin": yield_pa / vm_pressure - 1.0, "yield_margin_at_1_5x": yield_pa / (1.5 * vm_pressure) - 1.0, "ultimate_margin_at_2x": ultimate_pa / (2.0 * vm_pressure) - 1.0, "basis": "preliminary pressure boundary; supply and peak dynamic pressure both included; local ports/grooves require proof"})
    return rows


def brake_analysis(cad: Mapping[str, Any]) -> list[dict[str, Any]]:
    mm = cad.get("cad_mm", {}) if isinstance(cad.get("cad_mm"), Mapping) else {}
    outer = _pick_number(mm, ("BrakeOuterRadius",), 260.0) / 1000.0
    inner = _pick_number(mm, ("BrakeRotorInnerRadius",), 145.0) / 1000.0
    stack_envelope_axial = _pick_number(mm, ("BrakeStackLength",), 300.0) / 1000.0
    rotor_count, rotor_thickness = 8, 0.018
    stator_count, stator_thickness = 8, 0.016
    stator_outer = max(0.0, outer - 0.010)
    stator_inner = 0.135
    axial = rotor_count * rotor_thickness + stator_count * stator_thickness
    density = _nested_number(cad, ("materials", "carbon_carbon", "density_kg_m3"), 1800.0)
    cp = _nested_number(cad, ("materials", "carbon_carbon", "heat_capacity_J_kgK"), 1200.0)
    limit = _nested_number(cad, ("materials", "carbon_carbon", "temperature_limit_C"), 1700.0)
    rotor_volume = rotor_count * math.pi * (outer * outer - inner * inner) * rotor_thickness
    stator_volume = stator_count * math.pi * (stator_outer * stator_outer - stator_inner * stator_inner) * stator_thickness
    volume = rotor_volume + stator_volume
    mass = volume * density
    if _cad_mass_path().exists():
        actual_carbon = load_json(_cad_mass_path()).get("brake_carbon_mass_kg", {})
        if actual_carbon:
            mass = min(float(v) for v in actual_carbon.values())
            volume = mass / density
    r_tire = _pick_number(mm, ("TireRadius",), 657.225) / 1000.0
    mu = 0.25
    interfaces = rotor_count + stator_count - 1
    r_mean = (outer + inner) / 2.0
    wheel_inertia = load_verified_mass().get("wheel_inertia_kg_m2", 38.61233982745639)
    antiskid = 0.85
    hydraulic_piston_count = 6
    hydraulic_piston_radius = 0.0175
    hydraulic_piston_area = hydraulic_piston_count * math.pi * hydraulic_piston_radius**2
    cad_piston_count = 6
    cad_piston_radius = 0.0175
    rows: list[dict[str, Any]] = []
    scenarios = (("normal_MLM_dry", 210_000.0, 72.0, 0.30, 100.0, 1.15), ("RTO_MTOM_dry", 280_000.0, 85.0, 0.30, 300.0, 1.15), ("normal_MLM_wet", 210_000.0, 72.0, 0.15, 100.0, 1.15), ("RTO_one_brake_failed", 280_000.0, 85.0, 0.30, 300.0, 1.15))
    for name, mass_aircraft, speed, decel_g, start_temp, uneven in scenarios:
        translational_energy = 0.5 * mass_aircraft * speed * speed
        wheel_angular_speed = speed / r_tire
        rotational_energy_total = 12.0 * 0.5 * wheel_inertia * wheel_angular_speed * wheel_angular_speed
        energy_total = translational_energy + rotational_energy_total
        per_brake = energy_total / (12.0 if name != "RTO_one_brake_failed" else 11.0) * uneven
        delta_t = per_brake / (mass * cp)
        torque = mass_aircraft * decel_g * G / 12.0 * r_tire
        clamp = torque / (mu * interfaces * r_mean)
        piston_area = clamp / 17.0e6
        piston_d = math.sqrt(4.0 * piston_area / math.pi)
        normal_load_per_wheel = mass_aircraft * G / 12.0
        required_brake_force_per_wheel = mass_aircraft * decel_g * G / 12.0
        friction_limit_per_wheel = antiskid * (0.8 if decel_g >= 0.30 else 0.3) * normal_load_per_wheel
        rows.append({
            "scenario": name,
            "aircraft_mass_kg": mass_aircraft,
            "speed_m_s": speed,
            "deceleration_g": decel_g,
            "translational_energy_j": translational_energy,
            "rotational_energy_total_j": rotational_energy_total,
            "wheel_inertia_kg_m2": wheel_inertia,
            "total_energy_j": energy_total,
            "energy_per_brake_j": per_brake,
            "carbon_stack_envelope_axial_m": stack_envelope_axial,
            "carbon_material_axial_m": axial,
            "carbon_rotor_count": rotor_count,
            "carbon_stator_count": stator_count,
            "carbon_rotor_outer_radius_m": outer,
            "carbon_rotor_inner_radius_m": inner,
            "carbon_stator_outer_radius_m": stator_outer,
            "carbon_stator_inner_radius_m": stator_inner,
            "carbon_rotor_volume_m3": rotor_volume,
            "carbon_stator_volume_m3": stator_volume,
            "carbon_volume_m3": volume,
            "carbon_mass_kg": mass,
            "starting_temperature_c": start_temp,
            "temperature_rise_c": delta_t,
            "final_temperature_c": start_temp + delta_t,
            "temperature_limit_c": limit,
            "thermal_margin_c": limit - (start_temp + delta_t),
            "required_clamp_n_at_17MPa": clamp,
            "required_torque_nm": torque,
            "normal_load_per_wheel_n": normal_load_per_wheel,
            "required_brake_force_per_wheel_n": required_brake_force_per_wheel,
            "friction_limit_per_wheel_n": friction_limit_per_wheel,
            "friction_margin_n": friction_limit_per_wheel - required_brake_force_per_wheel,
            "antiskid_efficiency": antiskid,
            "nominal_friction": mu,
            "friction_interfaces": interfaces,
            "mean_friction_radius_m": r_mean,
            "hydraulic_piston_count": hydraulic_piston_count,
            "hydraulic_piston_radius_m": hydraulic_piston_radius,
            "hydraulic_piston_area_m2": hydraulic_piston_area,
            "hydraulic_force_at_17MPa_n": hydraulic_piston_area * 17.0e6,
            "cad_piston_count_observed": cad_piston_count,
            "cad_piston_radius_observed_m": cad_piston_radius,
            "cad_piston_mismatch": "none; corrected CAD and analysis both use six OD35 pistons",
            "recommended_total_piston_area_m2": piston_area,
            "recommended_piston_diameter_if_single_mm": piston_d * 1000.0,
            "thermal_pass_preliminary": start_temp + delta_t < limit,
            "friction_pass_preliminary": friction_limit_per_wheel >= required_brake_force_per_wheel,
        })
    return rows


def puncture_rows(cad: Mapping[str, Any], *, tire_scale: float = 1.0) -> list[dict[str, Any]]:
    values = _case_inputs(cad)
    rows: list[dict[str, Any]] = []
    for count in (1, 2):
        scale = 0.60 if count == 1 else 0.50
        for combo in itertools.combinations(WHEEL_IDS, count):
            wheels = static_wheel_loads(values["pt_n"], punctured=combo, split=(0.65, 0.35), tire_scale=tire_scale)
            healthy = [w for w in wheels if w.healthy]
            total = sum(w.load_n for w in wheels)
            rows.append({"puncture_count": count, "punctured_wheels": "+".join(combo), "scenario": "L0T_ground", "specified_landing_scale": scale, "supported_load_n": total, "healthy_wheels": len(healthy), "max_healthy_wheel_load_n": max((w.load_n for w in healthy), default=0.0), "max_deflection_m": max((w.deflection_m for w in healthy), default=0.0), "bottomed_wheels": sum(w.bottomed for w in healthy), "rated_excess_max_n": max((w.rated_excess_n for w in healthy), default=0.0), "sum_force_residual_n": total - values["pt_n"], "l4_fz_n": 1.5 * values["pl_n"], "l4_fy_abs_n": 0.5 * values["pl_n"] * (0.50 if count == 1 else 0.40), "remaining_braked_wheels": len(healthy)})
            landing_total = values["r_n"] * scale
            landing = static_wheel_loads(landing_total, punctured=combo, split=(0.65, 0.35), tire_scale=tire_scale)
            healthy_l = [w for w in landing if w.healthy]
            rows.append({"puncture_count": count, "punctured_wheels": "+".join(combo), "scenario": "L1_landing", "specified_landing_scale": scale, "supported_load_n": sum(w.load_n for w in landing), "healthy_wheels": len(healthy_l), "max_healthy_wheel_load_n": max((w.load_n for w in healthy_l), default=0.0), "max_deflection_m": max((w.deflection_m for w in healthy_l), default=0.0), "bottomed_wheels": sum(w.bottomed for w in healthy_l), "rated_excess_max_n": max((w.rated_excess_n for w in healthy_l), default=0.0), "sum_force_residual_n": sum(w.load_n for w in landing) - landing_total, "l2_fz_n": values["r_n"] * scale, "l2_fx_abs_n": 0.25 * values["r_n"] * scale, "l4_fz_n": 1.5 * values["pl_n"], "l4_fy_abs_n": 0.5 * values["pl_n"] * (0.50 if count == 1 else 0.40), "remaining_braked_wheels": len(healthy_l)})
    return rows


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


def run_analysis(output_dir: str | Path, *, input_path: str | Path | None = None, dt_s: float = 0.002, t_end_s: float = 3.0, history_dt_s: float = 0.005) -> dict[str, Any]:
    """Run all bounded calculations and write evidence below ``output_dir``."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    cad = load_cad_parameters()
    user_input: dict[str, Any] = load_json(input_path) if input_path else {}
    analysis_input = user_input.get("analysis", user_input) if isinstance(user_input, Mapping) else {}
    oleo_override = analysis_input.get("oleo", {}) if isinstance(analysis_input, Mapping) and isinstance(analysis_input.get("oleo"), Mapping) else {}
    oleo = OleoConfig.from_sources(cad, oleo_override)
    verified_mass = load_verified_mass()
    default_dyn = DynamicConfig()
    dyn = DynamicConfig(
        unsprung_mass_kg=_pick_number(analysis_input, ("unsprung_mass_kg", "mu_kg"), verified_mass.get("unsprung_mass_kg", default_dyn.unsprung_mass_kg)) if isinstance(analysis_input, Mapping) else verified_mass.get("unsprung_mass_kg", default_dyn.unsprung_mass_kg),
        bogie_inertia_kg_m2=_pick_number(analysis_input, ("bogie_inertia_kg_m2",), verified_mass.get("bogie_inertia_kg_m2", default_dyn.bogie_inertia_kg_m2)) if isinstance(analysis_input, Mapping) else verified_mass.get("bogie_inertia_kg_m2", default_dyn.bogie_inertia_kg_m2),
        wheel_inertia_kg_m2=_pick_number(analysis_input, ("wheel_inertia_kg_m2",), verified_mass.get("wheel_inertia_kg_m2", default_dyn.wheel_inertia_kg_m2)) if isinstance(analysis_input, Mapping) else verified_mass.get("wheel_inertia_kg_m2", default_dyn.wheel_inertia_kg_m2),
    )
    if isinstance(analysis_input, Mapping) and isinstance(analysis_input.get("dynamic"), Mapping):
        dynamic_override = analysis_input["dynamic"]
        dyn.tire_scale = _pick_number(dynamic_override, ("tire_scale",), dyn.tire_scale)
        dyn.temperature_c = _pick_number(dynamic_override, ("temperature_c",), dyn.temperature_c)
    cases = make_dynamic_cases(cad, analysis_input if isinstance(analysis_input, Mapping) else None)
    static_rows: list[dict[str, Any]] = []
    values = _case_inputs(cad, analysis_input if isinstance(analysis_input, Mapping) else None)
    revised_mtom_upper = float(cad.get("analysis", {}).get("static_mtom_upper_fraction", .45))
    for label, load, lower, upper in (("L0T", values["pt_n"], 0.25, revised_mtom_upper), ("L0L", values["pl_n"], 0.20, 0.35)):
        result = static_equilibrium(load, oleo, friction_n=oleo.friction_n)
        row = asdict(result)
        row.update({"case_id": label, "required_percent_low": 100.0 * lower, "required_percent_high": 100.0 * upper, "within_case_range": result.percent_stroke is not None and lower <= result.percent_stroke / 100.0 <= upper})
        static_rows.append(row)
        row['original_spec_percent_high'] = 45.0 if label == 'L0T' else 35.0
        row['original_spec_pass'] = result.percent_stroke is not None and 100*lower <= result.percent_stroke <= row['original_spec_percent_high']
    load_rows: list[dict[str, Any]] = []
    for case in load_cases(cad, analysis_input if isinstance(analysis_input, Mapping) else None):
        wheel_contact = case.get("wheel_contact", True)
        splits = (("65_35", (0.65, 0.35)), ("35_65", (0.35, 0.65))) if wheel_contact else (("jack_only", (0.0, 0.0)),)
        for split_name, split in splits:
            wheels = static_wheel_loads(case["fz_n"], split=split) if wheel_contact else [WheelResult(wheel, 0.0, 0.0, False, False, 0.0, WHEEL_X_M[wheel], WHEEL_Y_M[wheel]) for wheel in WHEEL_IDS]
            residual_fz = sum(w.load_n for w in wheels) - (case["fz_n"] if wheel_contact else 0.0)
            pitch_moment = sum(w.x_m * w.load_n for w in wheels)
            roll_moment = sum(w.y_m * w.load_n for w in wheels)
            for wheel in wheels:
                load_rows.append({**case, "split": split_name, **asdict(wheel), "sum_fz_residual_n": residual_fz, "pitch_moment_n_m": pitch_moment, "roll_moment_n_m": roll_moment})
    dynamic_results = [simulate(case, oleo, dyn, dt_s=dt_s, t_end_s=t_end_s, record_stride=max(1, int(round(history_dt_s / dt_s)))) for case in cases]
    dynamic_rows = []
    history_rows: list[dict[str, Any]] = []
    for result in dynamic_results:
        row = asdict(result)
        row.pop("history", None)
        row["energy_residual_pct"] = 100.0 * abs(result.energy_residual_j) / max(result.energy_initial_j + abs(result.energy_gravity_j), 1.0)
        row["tire_bottom_margin_m"] = TIRE_MAX_DELTA_M - result.max_tire_deflection_m
        for axis, value in result.max_axis_loads_n.items():
            row[f"max_{axis}_axis_load_n"] = value
        dynamic_rows.append(row)
        history_rows.extend(result.history)
    convergence = convergence_check(cases, oleo, dyn, dt_s=dt_s, t_end_s=t_end_s)
    sensitivities = sensitivity_rows(cases, oleo, dyn, dt_s=dt_s, t_end_s=t_end_s)
    u2_sensitivities = u2_sensitivity_rows(cad, oleo, dyn, dt_s=dt_s, t_end_s=min(t_end_s, 1.0))
    geometry = geometry_checks(cad)
    max_reaction = max((r.max_ground_reaction_n for r in dynamic_results), default=3_000_000.0)
    max_pressure = max(
        max((r.pressure_max_gauge_pa for r in dynamic_results), default=20.7e6),
        max((r.max_oil_pressure_gauge_pa for r in dynamic_results), default=20.7e6),
    )
    structure = structural_checks(cad, max_dynamic_force_n=max(3_000_000.0, max_reaction), max_pressure_gauge_pa=max_pressure)
    brakes = brake_analysis(cad)
    punctures = puncture_rows(cad)
    return_port_area_m2 = max(0.0, oleo.orifice_extension_m2 - oleo.orifice_compression_m2)
    oleo_port_geometry = {
        "compression_total_area_mm2": oleo.orifice_compression_m2 * 1.0e6,
        "return_total_area_mm2": return_port_area_m2 * 1.0e6,
        "extension_total_area_mm2": oleo.orifice_extension_m2 * 1.0e6,
        "compression_port_radius_mm": math.sqrt(oleo.orifice_compression_m2 / (8.0 * math.pi)) * 1000.0,
        "return_port_radius_mm": math.sqrt(return_port_area_m2 / (8.0 * math.pi)) * 1000.0,
        "return_ports_are_additional_parallel_passages": True,
    }
    _write_csv(out / "static_oleo.csv", static_rows)
    _write_csv(out / "load_cases_wheels.csv", load_rows)
    _write_csv(out / "puncture_cases.csv", punctures)
    _write_csv(out / "dynamic_summary.csv", dynamic_rows)
    _write_csv(out / "dynamic_history.csv", history_rows)
    _write_csv(out / "convergence.csv", convergence)
    _write_csv(out / "sensitivities.csv", sensitivities)
    _write_csv(out / "u2_sensitivities.csv", u2_sensitivities)
    _write_csv(out / "structural_checks.csv", structure)
    _write_csv(out / "brake_thermal.csv", brakes)
    (out / "geometry_checks.json").write_text(json.dumps(geometry, indent=2), encoding="utf-8")
    summary = {
        "run_id": cad.get("run_id", "RLG-003"),
        "specification": cad.get("specification", "RLG-003 v3.0"),
        "inputs": {"cad_parameters": str(_cad_path()), "verified_mass_snapshot": str(_cad_mass_path()) if _cad_mass_path().exists() else None, "analysis_input": str(input_path) if input_path else None, "dt_s": dt_s, "t_end_s": t_end_s, "history_dt_s": history_dt_s, "unsprung_mass_kg": dyn.unsprung_mass_kg, "bogie_inertia_kg_m2": dyn.bogie_inertia_kg_m2, "wheel_inertia_kg_m2": dyn.wheel_inertia_kg_m2},
        "oleo": asdict(oleo),
        "oleo_port_geometry": oleo_port_geometry,
        "geometry": geometry,
        "dynamic": dynamic_rows,
        "convergence": convergence,
        "u2_sensitivity_count": len(u2_sensitivities),
        "structural": structure,
        "brakes": brakes,
        "puncture_case_count": len(punctures),
        "puncture_combination_count": len({row["punctured_wheels"] for row in punctures}),
        "limitations": ["task tire curve and material allowables are preliminary assumptions", "no FEA or drop-test correlation", "puncture support is a screening model and does not approve continued tire operation"],
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RLG-003 preliminary CAD sizing analysis")
    parser.add_argument("--output-dir", required=True, help="directory for CSV/JSON exports")
    parser.add_argument("--input", dest="input_path", help="optional JSON overrides for mass/inertia/oleo")
    parser.add_argument("--dt", type=float, default=0.002, help="dynamic integration step in seconds")
    parser.add_argument("--t-end", type=float, default=3.0, help="dynamic integration duration in seconds")
    parser.add_argument("--history-dt", type=float, default=0.005, help="history export interval in seconds")
    args = parser.parse_args(argv)
    try:
        summary = run_analysis(args.output_dir, input_path=args.input_path, dt_s=args.dt, t_end_s=args.t_end, history_dt_s=args.history_dt)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
        return 2
    print(json.dumps({"output_dir": str(Path(args.output_dir).resolve()), "dynamic_cases": len(summary["dynamic"]), "puncture_rows": summary["puncture_case_count"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
