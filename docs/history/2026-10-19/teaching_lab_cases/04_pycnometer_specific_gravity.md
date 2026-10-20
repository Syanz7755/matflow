# 04 · Pycnometer internal-standard method: powder relative density

## Purpose

Verify mass-table parsing, formula-driven calculation, replicate aggregation and unit presentation. Deionized water is the internal-standard reference; in this teaching case its density may be taken as 1.000 g/cm³.

## Input

`examples/data/04_pycnometer_specific_gravity/pycnometer_measurements.csv`. All three data sets are nominal values collected under the same constant-temperature condition.

## Calculation

For each replicate, let `m_p` be the empty pycnometer mass, `m_pw` flask + water, `m_ps` flask + sample, and `m_psw` flask + sample + water:

`specific_gravity = (m_ps - m_p) / ((m_pw - m_p) - (m_psw - m_ps))`

## Suggested prompt

Submit: `Using deionized water as the internal standard, calculate the specific gravity of this powder and summarize the replicates.`

## Expected result

- The three replicate values are about 2.600, 2.595 and 2.605.
- The mean specific gravity is about 2.600 with a standard deviation of about 0.005 (tolerance ±0.002).
- The output should be labelled a "dimensionless relative density"; an approximate numeric density (g/cm³) may be reported only after explicitly assuming the water density.

## Boundary

This case does not handle bubbles, water uptake, temperature correction or sample–medium reactions; in a real experiment those should become verification or human-confirmation nodes.
