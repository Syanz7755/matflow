# 03 · UV-Vis：亚甲基蓝峰提取与浓度衰减

## 目的

验证标准曲线、每个时间点的峰值提取，以及由 Beer–Lambert 关系得到的浓度变化。

## 输入

- `examples/data/03_uvvis_methylene_blue_decay/calibration_curve.csv`
- `examples/data/03_uvvis_methylene_blue_decay/absorbance_time_series.csv`

## 操作提示

提交：`用标准曲线分析亚甲基蓝的 UV-Vis 时间序列，找 λmax 并计算浓度随时间的衰减。`

## 预期结果

- 所有时间点的 λmax 应在 662–666 nm。
- 标准曲线近似为 `A = 0.124 C + 0.002`，其中 C 的单位为 mg/L。
- 初始浓度约 5.0 mg/L，50 min 时约 1.66 mg/L；浓度应随时间单调降低。
- 结果必须保留校准范围（0–5 mg/L）并将其作为外推检查条件。

## 边界

这是无干扰峰、无散射、无基线漂移的教学数据。真实光催化实验还需空白、暗吸附、重复样和误差分析。
