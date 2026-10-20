# Case 6: `long_uvvis_01_decay_kinetics`

- domain: `uvvis`
- language: `zh`
- intent: `routing_only`
- fixture hint: `examples/data/03_uvvis_methylene_blue_decay/absorbance_time_series.csv`
- expected route: `(none)` (capability missing)
- last observed route verdict: **expected_unsupported**
- last observed selection: `ebrick_case05_import` (confidence 0.5, 3 candidate(s))
- route expectation: This capability is NOT registered in the composed workspace (only EIS, generic input/transform/control nodes and the EBrick case tools are active), so no tool may be selected. Any selection would be a false match.
- why this prompt is long: Two coupled datasets, a photodegradation narrative and a fitting request.

Prompt length: 589 characters.

## Input prompt

```text
【实验目的】我在做亚甲基蓝的光催化降解实验，催化剂是自制的 g-C3N4 粉体，想通过吸光度随时间的下降来推算降解动力学，判断反应是一级还是零级。
【实验条件】亚甲基蓝初始浓度约 10 mg/L，溶液体积 50 mL，催化剂投加量 0.05 g，先暗吸附 30 分钟达到吸附平衡，然后用 300 W 氙灯照射，灯距 15 cm，配 420 nm 截止滤光片。每隔 10 分钟取样 3 mL，离心后取上清液测吸光度，一共测到 60 分钟。
【数据说明】我有两个 CSV。第一个是标准曲线数据，两列：concentration_mg_per_L 和 absorbance，是在 664 nm 处测的，用来把吸光度换算成浓度。第二个是时间序列，两列：time_min 和 absorbance_664，注意 0 分钟对应的不是初始浓度，而是暗吸附结束之后的浓度，这一点在做动力学拟合时很关键。
【请求】1) 先用标准曲线把时间序列的吸光度换算成浓度，报告你会用线性拟合还是原点强制过零，并说明理由。2) 提取 664 nm 处的最大吸收峰，确认它随时间是否单调下降；如果有异常点请指出。3) 计算 ln(C0/Ct) 对时间的关系，判断更接近一级还是零级动力学，给出拟合优度和你的判断依据。4) 明确说明：只凭吸光度数据能否排除催化剂吸附和光解两个干扰，如果不能，需要补哪些对照实验。
```
