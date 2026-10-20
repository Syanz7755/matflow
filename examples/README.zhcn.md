# MatFlow 示例案例包

本目录只保留两个快速演示案例：EIS 基础质控和 XRD 锐钛矿识别。它们不属于 Platform Core 或产品设计文档，也不能替代真实实验数据、仪器软件或研究结论。

## 使用方式

1. 在项目根目录执行 `uv run python examples/generate_example_data.py`，可确定性地重新生成所有 CSV 输入数据。
2. 选择 `examples/docs/` 中的一份案例说明，将对应目录中的 CSV 上传或导入 MatFlow。
3. 将实际路由结果、图状态和结构化结果，与文档中的验收条件比对。

扩展的教学实验回归包仅用于测试；套件、夹具和脚本分别位于 `tests/suites/`、`tests/fixtures/teaching_lab/` 和 `tests/tools/`。

生成脚本不依赖随机数；重复运行会得到相同的测试输入。案例中的预期结果是对合成数据的已知答案，允许有明确的数值容差。

## 案例索引

| ID | 主题 | 主要输入 | 已知预期 |
| --- | --- | --- | --- |
| `01_eis_basic_qc` | EIS 基础质控与 Nyquist 图 | 阻抗频率扫描 | 全部点有效；高频截距约 5 Ω |
| `02_xrd_anatase_identification` | XRD 晶相识别 | 2θ–强度谱 | 主相为 anatase TiO₂；特征峰约 25.3° |

提示词变体、回归套件和生成的评测报告应放在 `tests/` 或被忽略的 `.tmp/` 目录。历史输出保存在 `docs/history/2026-10-19/`，不能作为当前能力证据引用。
