# MatFlow 示例案例包

本目录保存 **仅用于开发、演示和回归测试** 的材料学教学级 Reference Case；它不属于 Platform Core 或产品设计文档，也不能替代真实实验数据、仪器软件或研究结论。案例中出现的数据类型、Tool 和预期结果只有在明确归入 Domain Package 后才可复用，不能直接提升为核心内置能力。

## 使用方式

1. 在项目根目录执行 `uv run python examples/generate_example_data.py`，可确定性地重新生成所有 CSV 输入数据。
2. 选择 `examples/docs/` 中的一份案例说明，将对应目录中的 CSV 上传或导入 MatFlow。
3. 将实际路由结果、图状态和结构化结果，与文档中的验收条件比对。

扩展的教学实验 prompt 回归包见 `docs/07_teaching_lab_prompt_suite.md`。它包含 15 个流程、64 条输入、合成数据的基线结果，以及离线验收入口 `test_teaching_lab_suite.bat`。

生成脚本不依赖随机数；重复运行会得到相同的测试输入。案例中的预期结果是对合成数据的已知答案，允许有明确的数值容差。

## 案例索引

| ID | 主题 | 主要输入 | 已知预期 |
| --- | --- | --- | --- |
| `01_eis_basic_qc` | EIS 基础质控与 Nyquist 图 | 阻抗频率扫描 | 全部点有效；高频截距约 5 Ω |
| `02_xrd_anatase_identification` | XRD 晶相识别 | 2θ–强度谱 | 主相为 anatase TiO₂；特征峰约 25.3° |
| `03_uvvis_methylene_blue_decay` | UV-Vis 峰提取和浓度衰减 | 标准曲线、时间序列光谱 | λmax 约 664 nm；浓度单调下降 |
| `04_pycnometer_specific_gravity` | 比重瓶内标相对密度 | 空瓶、加水、加样质量 | 平均比重约 2.60 |
| `05_tga_caco3_content` | TGA 失重估算碳酸钙含量 | 温度–残余质量 | CaCO₃ 质量分数约 20.0% |

## 长提示词流程打印套件

`long_prompt_cases.json` 是一组**刻意写长**的提示词（16 条，389–2124 字符，合计约 11.5k 字符），
用于检查后端在长输入下的路由行为，以及 `flowview` 在长输入下的打印效果。每条案例都带有
`expected_route` / `route_expectation_note` / `observed_route` / `route_verdict`
（`as_expected` / `expected_unsupported` / `misrouted`），因此错误路由会被**如实记录**而不是被默默接受。

```powershell
.\.venv\Scripts\python.exe -m flowview.tools.run_prompt_cases `
  --suite examples/long_prompt_cases.json `
  --out   examples/reports/prompt_flows
```

产物：`examples/reports/prompt_flows/INDEX.md`（汇总与路由观察）、`PROMPTS.md`（全部提示词原文）、
每条案例的 `prompt.md` + `flow-prompt.{mermaid,text.txt,json.txt}`、`_stages/`（后端七阶段蓝图）
与 `_task/`（真实记录任务）。运行说明见 `flowview/README.md`。

注意：这些提示词是合成测试输入，不是科学结论，也不是 Reference Case；其中的路由结果来自**确定性词法
检索器**（未启用 JEV 模型路由），因此可离线复现。

每个案例也包含一个刻意受限的解释边界：它测试工具选择、参数校验、执行和结果呈现，不测试真正的自动科学发现。
