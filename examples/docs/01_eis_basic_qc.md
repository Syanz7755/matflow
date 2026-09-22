# 01 · EIS 基础质控与 Nyquist 图

## 目的

验证从阻抗 CSV 导入、列映射、EIS 质控和 Nyquist 绘图的最小闭环。

## 输入

`examples/data/01_eis_basic_qc/eis_spectrum.csv`。必需列为 `frequency_hz`、`z_real_ohm` 和 `z_imag_ohm`；频率单位为 Hz，阻抗单位为 Ω。

## 操作提示

提交：`对这组 EIS 数据做基础质量检查并绘制 Nyquist 图。`

## 预期结果

- 路由应选中 `eis_basic_qc`，并在其后连接 `plot_nyquist`（或由用户确认该绘图步骤）。
- 13 个数据点均为有限数值，频率全为正数。
- 高频端的实部阻抗约为 5.0 Ω（允许 ±0.2 Ω）。
- UI 应展示结构化质控结果、图节点状态与 trace ID；不得把虚部正负号静默改写。

## 边界

这是一个理想化的 `R(RC)` 合成谱，不用于等效电路拟合真实性验证。
