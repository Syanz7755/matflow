# Case 4: `long_xrd_02_residual_stress`

- domain: `xrd`
- language: `en`
- intent: `routing_only`
- fixture hint: `examples/data/02_xrd_anatase_identification/xrd_anatase.csv`
- expected route: `(none)` (capability missing)
- last observed route verdict: **expected_unsupported**
- last observed selection: `ebrick_cp_g_qc` (confidence 1.0, 9 candidate(s))
- route expectation: This capability is NOT registered in the composed workspace (only EIS, generic input/transform/control nodes and the EBrick case tools are active), so no tool may be selected. Any selection would be a false match.
- why this prompt is long: English long-form prompt with instrument context and a deliberately broad scope.

Prompt length: 1553 characters.

## Input prompt

```text
Context: this pattern was collected on a thin-film TiO2 sample grown by atomic layer deposition on a Si (100) substrate, 120 nm nominal thickness, measured on a Bruker D8 Discover in parallel-beam geometry with a Gobel mirror, Cu Kalpha radiation at 1.5406 Angstrom, generator 40 kV / 40 mA. The scan covers 2theta from 15 to 75 degrees with a 0.02 degree step and 1 second per step; the sample was spun during measurement to average out any texture, and no monochromator was used on the diffracted beam, so Kalpha2 is present.
Data layout: the CSV has two columns, two_theta_deg and intensity_counts. The first few rows include the raw header the instrument writes, and the intensity baseline drifts slightly upward across the scan because of sample fluorescence.
What I need, in this order: (1) extract the diffraction peaks and report the 2theta position, relative intensity and full width at half maximum for each peak you consider real; (2) tell me which phase or phases are present and state the criteria you used, i.e. which peaks are diagnostic and which ones would falsify the assignment; (3) comment on whether the peak widths are consistent with a nanocrystalline film, and be explicit that this is an inference rather than a measurement.
Constraints: stay within the registered tools; do not invent a peak-fitting method that is not available. If a required capability is missing, name the capability precisely and list the parameters a human must confirm before anything is executed. Do not silently guess the wavelength or the zero offset.
```
