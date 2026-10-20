# 05 · TGA: estimating CaCO₃ content from decarbonation mass loss

## Purpose

Verify temperature–mass curve handling, calculation over a specified mass-loss window, and stoichiometric conversion.

## Input

`examples/data/05_tga_caco3_content/tga_mass_loss.csv`, containing temperature over 30–900 °C and normalized residual mass percentage.

## Suggested prompt

Submit: `Estimate the CaCO3 mass fraction of the sample from the 600–850 °C mass-loss step.`

## Expected result

- The mass is essentially 100% before 600 °C and the plateau after 850 °C is about 91.20%.
- The decarbonation mass loss is about 8.80 wt%.
- Using `w(CaCO3) = w(CO2) × 100.09 / 44.01` gives about 20.0 wt% CaCO₃ (tolerance ±0.5 wt%).
- The result must record the temperature window and the stoichiometric assumption explicitly.

## Boundary

The conversion assumes all mass loss in this temperature region comes from CaCO₃ → CaO + CO₂. A real sample requires excluding other carbonates, volatiles and baseline drift.
