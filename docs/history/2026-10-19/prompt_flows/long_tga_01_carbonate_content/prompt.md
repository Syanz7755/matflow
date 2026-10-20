# Case 7: `long_tga_01_carbonate_content`

- domain: `tga`
- language: `zh`
- intent: `routing_only`
- fixture hint: `examples/data/05_tga_caco3_content/tga_mass_loss.csv`
- expected route: `(none)` (capability missing)
- last observed route verdict: **expected_unsupported**
- last observed selection: `ebrick_case05_import` (confidence 0.25, 1 candidate(s))
- route expectation: This capability is NOT registered in the composed workspace (only EIS, generic input/transform/control nodes and the EBrick case tools are active), so no tool may be selected. Any selection would be a false match.
- why this prompt is long: Thermal analysis with purge gas, heating rate and a stoichiometry discussion.

Prompt length: 605 characters.

## Input prompt

```text
【样品与装置】样品是石灰石粉体，粒径小于 75 微米，取 12.5 mg 左右装在氧化铝坩埚里，参比为空坩埚。仪器是 TA Instruments SDT Q600 同步热分析仪，气氛为高纯氮气，流量 100 mL/min，升温速率 10 °C/min，温度范围 30 到 1000 °C，分别在 105 °C 和 600 °C 做了两次恒温 10 分钟，用来把吸附水和结构水分开。
【数据说明】导出的两列是 temperature_C 和 mass_percent，质量百分比是以初始质量为基准归一化之后的。曲线上我肉眼看到三段明显失重：120 °C 之前有个小台阶，大约 400 到 500 °C 之间有一段，600 到 800 °C 之间还有一段大的，我猜最后一段是碳酸钙分解成氧化钙并放出二氧化碳。
【请求】1) 找出各个失重台阶的起止温度和对应的质量损失百分比。2) 根据高温段的质量损失，按 CaCO3 分解为 CaO 和 CO2 的化学计量关系估算样品中碳酸钙的质量分数，并写出你用到的摩尔质量。3) 报告不确定度来源，至少包括基线漂移、浮力效应和恒温段的选择对结果的影响。4) 明确写出：这份数据能否区分碳酸钙和碳酸镁，为什么。
【约束】不要假设所有失重都来自碳酸钙；如果 400-500 °C 那段更可能是别的分解反应，请说明理由并提出需要补充的证据。只使用已注册工具，如缺失能力请直接说明。
```
