# RLG-003 user decisions

- 2026-10-22 (America/Los_Angeles): The user confirmed RLG-003 v3.0, six-wheel retractable main gear as the design target.
- The immediate deliverable is the landing-gear CAD. The web viewer and publication are a later step.
- CalculiX is excluded. Engineering calculations use the project's own Python implementation.
- Physical auxiliary springs are authorized to retain the specified static sag bands.
- 2026-10-22: The user explicitly confirmed that the 6,000 kg mass target is not mandatory. Treat it as a reference value, report measured mass, and prioritize assembly integrity and operation. Mass exceedance alone is not a failure or a blocker.
- 2026-10-22: Replace the rectangular bay with a 777-class-inspired independent wing/body bay; actual retraction and stowage are required. Do not claim OEM internal geometry without drawings.
- The user rejected the unrealistic two large external load-bearing coil springs and transverse frames. Revision r02 returns to a conventional central oleo and removes that external assembly.
- The user authorized minimum justified specification changes, including approximately 47% rather than 45% MTOM static sag if needed. Preserve and report the original-spec result as well.
- This is an initial-design benchmark. Reasonable deviations and explicit NG results are acceptable; do not force a passing result through unrealistic architecture.
- Preserve failure-example images, CAD and available evidence. The r01 external-spring/rectangular-bay snapshot is fixed under outputs/failure_examples/r01_external_springs_rectangular_bay; later designs use r02 and must not overwrite it.
