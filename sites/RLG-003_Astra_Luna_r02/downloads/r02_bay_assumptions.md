# r02 aircraft-like bay assumptions

The user selected an independent 777-class concept, not an exact reconstruction of Boeing internal wheel-well geometry. The public [Boeing 777 airport-planning manual](https://www.boeing.com/content/dam/boeing/v2/airports/acaps/777-200-200ER-300_Rev_E.pdf) and [official manual index](https://www.boeing.com/commercial/airports/plan-manuals) provide aircraft configuration context; they do not establish the internal surfaces below.

The following surfaces are explicit design assumptions, implemented in `cad/rlg003/airframe_bay.py`:

- Maximum envelope retains RLG-003: X ±2300, Y −3400…300, Z ±1100 mm.
- Broad inboard wheel pocket; 450 mm rear-corner chamfers represent fairing/bulkhead constraints.
- Swept transition from the wheel pocket to a narrower wing mounting region, with X −1300…1100 mm at the outboard neck.
- Roof at Z=1050 over the wheel pocket, inclined between Y=−1650 and −1400 to Z=950 over the mounting region.
- A closed solid `RLG003_BayUsableSpace` defines the actual admissible space. It is hidden reference geometry, not a bottom wall.
- Physical 10 mm side and roof panels are outside the admissible space. The opening rim and shaped doors follow the nonrectangular plan.
- Closed doors retain the datum Z=−1110 and 10 mm thickness. Nominal perimeter gap is 2 mm and the central seam is 4 mm.
- Door motion remains an explicit preliminary 180-degree downward/outward hinge concept. It is not claimed to duplicate 777 door kinematics. Ground and swept-clearance results determine its benchmark status.

Containment must use the actual closed solid, not just the maximum rectangular envelope. A Pass for static containment does not certify the continuous retraction path. The CAD keeps the test fixture distinct from the bay; detailed fuselage/wing strength, actual pressure-shell structure and OEM approval drawings are outside this concept.

The earlier external-coil/rectangular-bay configuration is retained under `outputs/failure_examples/`. No later pass may overwrite its recorded failures.
