# Limitations

- This case replays one packaged historical stdout.  It does not launch
  Quantum ESPRESSO, Slurm, SSH, or any other HPC execution path.
- The fixed prompt labels the case for readers.  MatFlow selects this case from
  the explicit `demo qe-mgo` subcommand; no LLM planned it and no keyword router
  chose it.
- The input fixture names pseudopotentials, but the replay neither bundles nor
  validates those pseudopotential files.
- A converged historical SCF output does not establish that the same result can
  be reproduced on a new QE installation without the original executable,
  pseudopotentials, and compute environment.
- One pristine 2×2×2 MgO case does not validate other structures, defects,
  dopants, parameter settings, or materials.
- The fixture's declared upstream path is retained as provenance metadata only.
  This demo reads no live EBrick files or databases.
