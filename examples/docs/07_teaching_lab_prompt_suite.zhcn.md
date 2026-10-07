# 教学实验 Prompt 测试集（15 流程 / 64 输入）

这是 MatFlow 的离线、确定性回归案例包。它覆盖材料、大学化学和大学物理中的数据分析任务；所有 CSV 都是合成数据，只用于测试工具选择、输入校验、计算契约和结果呈现，**不是实验操作规程，也不能用于替代仪器软件或研究结论**。

## 文件与运行方式

- `examples/teaching_lab_prompt_suite.json`：15 个流程、每流程 4 种语言风格，以及 4 个跨流程/安全输入，共 64 条 prompt。
- `examples/teaching_lab_expected_results.json`：合成数据的已知结果，是可审阅的基线结果文件。
- `examples/generate_teaching_lab_suite.py`：确定性重建新增 CSV、prompt 文件和基线结果。
- `examples/verify_teaching_lab_suite.py --check`：验收脚本；运行报告写入被忽略的 `examples/reports/teaching_lab_acceptance.json`。
- `test_teaching_lab_suite.bat`：可双击的验收入口。

验收器不会调用 Jev、LiteLLM、外部检索或 Tool Manager；它验证案例包的格式、64 条输入覆盖、15 个流程、两项故意缺失的工具、文件存在性以及各合成数据的数值答案。

## Registry 语义

`existing_active` 表示现有可执行工具；`preset_candidate` 只表示将来的预置工具契约，不等同于已实现执行器；`tool_manager_required` 表示刻意缺省的能力。后两类在真实运行时不能标记为 `active` 或输出伪造科学结论。

两个缺省案例是 `rietveld_refinement` 与 `raman_mapping_analysis`。它们的正确行为是：提出候选工具的输入/输出契约、建议检索或适配路径、进入人工审核；不能直接执行或声称已得到精修/面扫描结论。

## 教学来源

案例的实验主题由公开高校教学资料选择，而不是复制其操作过程：MIT Materials Laboratory 覆盖 XRD、DSC、UV/Vis、Raman、FTIR 等表征；MIT 5.35 包含电子/红外光谱、Lambert–Beer 和动力学；MIT Junior Lab 和电子测量课程包含光电效应、Michelson 干涉和 RC 瞬态。

- <https://ocw.mit.edu/courses/3-014-materials-laboratory-fall-2006/pages/labs/>
- <https://ocw.mit.edu/courses/5-35-introduction-to-experimental-chemistry-fall-2012/pages/labs/>
- <https://live.ocw.mit.edu/courses/8-13-14-experimental-physics-i-ii-junior-lab-fall-2016-spring-2017/pages/experiments/photoelectric-effect/>
- <https://ocw.mit.edu/courses/8-13-14-experimental-physics-i-ii-junior-lab-fall-2016-spring-2017/7c85fcf2432fca75c26f9f78b6c8cb18_MIT8_13-14F16-S17expIII.pdf>
- <https://ocw.mit.edu/courses/6-071j-introduction-to-electronics-signals-and-measurement-spring-2006/491e7e50ee65521c601ee51d3c6f7e5f_lab15_transients.pdf>
