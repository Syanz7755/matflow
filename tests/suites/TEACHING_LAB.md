# Teaching-lab prompt suite (15 flows / 64 inputs)

This is MatFlow's offline, deterministic regression case pack. It covers data-analysis tasks from materials science, university chemistry and university physics; every CSV is synthetic data used only to test tool selection, input validation, calculation contracts and result presentation. It is **not an experimental procedure and cannot replace instrument software or research conclusions**.

## Files and how to run

- `tests/suites/teaching_lab_prompt_suite.json`: 15 flows with 4 language styles each, plus 4 cross-flow/safety inputs, 64 prompts in total.
- `tests/suites/teaching_lab_expected_results.json`: the known results for the synthetic data, a reviewable baseline-results file.
- `tests/tools/generate_teaching_lab_suite.py`: deterministically rebuilds the added CSVs, prompt files and baseline results.
- `tests/tools/verify_teaching_lab_suite.py --check`: the acceptance script; its run report is written to the ignored `.tmp/teaching_lab_acceptance.json`.
- `scripts/test_teaching_lab_suite.ps1`: a double-clickable acceptance entry point.

Cases 01 (EIS) and 02 (XRD) remain quick-start demos under `examples/`. Cases 03-15 are test fixtures under `tests/fixtures/teaching_lab/`; they are not demo cases.

The verifier calls no Jev, LiteLLM, external retrieval or Tool Manager; it validates the pack format, the 64-input coverage, the 15 flows, the two deliberately missing tools, file existence and the numeric answers for each synthetic dataset.

## Registry semantics

`existing_active` means an existing executable tool; `preset_candidate` means only a future preset tool contract and is not the same as an implemented executor; `tool_manager_required` means a deliberately absent capability. The latter two must not be marked `active` at real runtime or emit fabricated scientific conclusions.

The two absent cases are `rietveld_refinement` and `raman_mapping_analysis`. Their correct behavior is to propose the candidate tool's input/output contract, suggest a search or adaptation path and enter human review; they must not execute directly or claim a refinement / mapping conclusion.

## Teaching sources

Case topics were chosen from public university teaching material rather than copied from its procedures: the MIT Materials Laboratory covers XRD, DSC, UV/Vis, Raman and FTIR characterization; MIT 5.35 covers electronic and infrared spectroscopy, Lambert–Beer and kinetics; MIT Junior Lab and the electronics-measurement course cover the photoelectric effect, Michelson interference and RC transients.

- <https://ocw.mit.edu/courses/3-014-materials-laboratory-fall-2006/pages/labs/>
- <https://ocw.mit.edu/courses/5-35-introduction-to-experimental-chemistry-fall-2012/pages/labs/>
- <https://live.ocw.mit.edu/courses/8-13-14-experimental-physics-i-ii-junior-lab-fall-2016-spring-2017/pages/experiments/photoelectric-effect/>
- <https://ocw.mit.edu/courses/8-13-14-experimental-physics-i-ii-junior-lab-fall-2016-spring-2017/7c85fcf2432fca75c26f9f78b6c8cb18_MIT8_13-14F16-S17expIII.pdf>
- <https://ocw.mit.edu/courses/6-071j-introduction-to-electronics-signals-and-measurement-spring-2006/491e7e50ee65521c601ee51d3c6f7e5f_lab15_transients.pdf>
