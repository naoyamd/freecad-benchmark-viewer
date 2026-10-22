# r02 calculation methods

This is a self-implemented initial-design benchmark. No CalculiX or FEA solver is used. Failed requirements and uncertain details remain explicit. Superseded r01 methods are preserved in `outputs/failure_examples/r01_external_springs_rectangular_bay/r01_analysis_methods.md`.

## Architecture and inputs

One conventional central air/oil oleo supports the load. The two large external coil springs and their frames have been removed. Full-extension gas volume is 65 L, precharge 9.20 MPa absolute at 20 C, piston OD/ID 330/270 mm, barrel OD/ID 550/460 mm, and maximum stroke 600 mm. Auxiliary mechanical spring stiffness is zero.

Static gas exponent is 1; dynamic exponent is 1.3. Displacement area is the piston outside area. Hydraulic flow area is the barrel/piston annulus, 80,660.39 mm2. Eight compression passages total 2,900 mm2; eight additional check-valve passages provide 2,420 mm2, giving 5,320 mm2 total return area. Cd=0.65, oil density=870 kg/m3, seal friction=5 kN.

The lower annular chamber increases in volume during compression: p_upper=p_gas and p_lower=p_gas-delta_p. During rebound p_lower=p_gas+delta_p. Both chamber pressures, cavitation and dissipated work are recorded. Fluid reference solids are excluded from structural mass; real oil charge is reported separately.

## Authorized changes

A constant-area single gas chamber with at least 20% residual volume cannot simultaneously meet the specified light-load lower sag limit and heavy-load 45% upper limit. Current nominal MLM/MTOM sag is approximately 20.11%/46.56%. The user authorized a revised MTOM limit of 47%. `static_oleo.csv` retains the original-spec Fail and revised-condition Pass. The 6,000 kg target is a reference, not a mandatory gate.

## Dynamics and structure

`rlg003.py` integrates sprung/unsprung vertical motion and bogie pitch with six unilateral contacts, gas force, damping, stroke constraints and rebound. Landing mass is M/2. Current CAD mass and inertia are read from `cad_mass.json`. D1, D2, D3, D4a/b and D5, time-step halving, energy residuals and sensitivities are recorded. Tire curves and material properties remain design assumptions. Gross-section stresses do not establish local lug, key, thread, fatigue or proof-load qualification.

Brake calculations use machined CAD carbon mass (approximately 69.71 kg/wheel), 8 rotating 18 mm discs and 8 stationary 16 mm discs. Rotor OD/ID is 520/290 mm and stator OD/ID 500/270 mm. Fifteen interfaces and six OD35 pistons are used. Rotating and fixed keys exist in CAD. Supplier friction, thermal and bearing qualification is pending.

## Retraction and packaging

`motion_boundaries.py` extracts CAD mass positions and conservative projected-area bounds. `motion_dynamics.py` evaluates normal/emergency movement. The independent emergency accumulator is 12 L, precharged to 10 MPa absolute, charged to 20.7 MPa gauge, and enabled at theta<=20 degrees. Stop-energy absorption, flexible plumbing and timed lock completion require final evidence; reaching theta=0 alone is not a lock pass.

Static containment, wall/door clearance and continuous motion are separate checks. A time-limited sweep remains inconclusive. An unsaved inspection copy may freeze invariant dimension bindings only after matching volume within 1 ppm and bounding coordinates within 0.001 mm. The editable master is unchanged.

The shaped bay is an independent 777-class-inspired layout, not an OEM replica. See `docs/r02_bay_assumptions.md` and `docs/rlg003_user_decisions.md`. Earlier failure images and models are retained.
