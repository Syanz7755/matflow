# Case 13: `long_english_01_lab_report`

- domain: `eis`
- language: `en`
- intent: `route_then_execute`
- fixture hint: `examples/data/01_eis_basic_qc/eis_spectrum.csv`
- expected route: `(none)` (capability missing)
- last observed route verdict: **expected_unsupported**
- last observed selection: `ebrick_case05_import` (confidence 1.0, 9 candidate(s))
- route expectation: This capability is NOT registered in the composed workspace (only EIS, generic input/transform/control nodes and the EBrick case tools are active), so no tool may be selected. Any selection would be a false match.
- why this prompt is long: Long English lab-report style prompt with acceptance criteria and reporting format.

Prompt length: 2124 characters.

## Input prompt

```text
Please treat this as a formal analysis request and work only through the registered tools.
Sample and history: the specimen is a 1 mm thick sintered pellet of a garnet-type solid electrolyte, roughly 12 mm diameter, stored in a dry box for three weeks before measurement. The pellet was sputter-coated with gold on both faces and clamped between spring-loaded stainless steel contacts. Before the measurement the cell rested at open circuit for 30 minutes; the open-circuit voltage settled at 12 mV, which is small relative to any decomposition potential we care about, but I am mentioning it because you should note it as a possible source of a low-frequency artefact.
Instrument and settings: measurements ran on a Gamry Reference 600+ in potentiostatic EIS mode, 10 mV AC amplitude, no DC bias, from 1 MHz down to 0.1 Hz, 10 points per decade, giving 61 frequencies. The reported temperature is 25.0 plus or minus 0.5 degrees Celsius. Three repeated sweeps were taken back to back; I am giving you the first sweep only, and I expect you to say explicitly whether a single sweep is enough to claim repeatability.
Data layout: the CSV has a header line written by the instrument, then one blank line, then the columns frequency_Hz, Z_real_ohm and Z_imag_ohm. The imaginary part is negative for capacitive behaviour. If the file does not parse the way I described, tell me which line and what you saw rather than silently skipping rows.
What I need: (1) a basic quality check of the spectrum, covering monotonic frequency ordering, duplicate frequencies, outliers, negative real part, and whether the high-frequency end approaches a real-axis intercept; (2) a Nyquist plot from the valid points with -Z_imag on the vertical axis, and the high-frequency intercept value reported next to the plot; (3) a short verdict on whether this single sweep supports a claim about the bulk resistance, and if not, what additional data would be needed.
Boundaries: do not invent a model or a fitting procedure that is not available in the workspace; if a capability is missing, name it and list what a human must confirm before execution.
```
