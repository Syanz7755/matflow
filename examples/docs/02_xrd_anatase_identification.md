# 02 · XRD：Anatase TiO₂ 晶相识别

## 目的

验证 2θ–强度谱的列识别、峰提取及基于参考峰表的保守晶相建议。

## 输入

`examples/data/02_xrd_anatase_identification/xrd_anatase.csv`，列为 `two_theta_deg` 和 `intensity_counts`。扫描范围 20–70°，步长 0.125°。

## 操作提示

提交：`提取 XRD 峰，并判断这份样品最可能的 TiO2 晶相。`

## 预期结果

- 解析器将横轴识别为 2θ（degree）、纵轴识别为强度（counts）。
- 最高峰位置约为 25.25–25.38°；还应检测到约 37.8°、48.0°、53.9°、55.1°、62.7° 的次级峰。
- 结果应给出“与 anatase TiO₂ 特征峰一致”的**候选识别**，并注明需要参考数据库或标准卡片确认。
- 若 `xrd_phase_identification` 尚未注册，路由不得伪造执行结果；应返回需要确认/工具缺失的结构化状态。

## 边界

该谱是人工生成的 anatase-like 峰形，不能用于晶粒尺寸、微应变、Rietveld 定量或发表级相鉴定。
