# Case 3: `long_xrd_01_phase_identification`

- domain: `xrd`
- language: `zh`
- intent: `routing_only`
- fixture hint: `examples/data/02_xrd_anatase_identification/xrd_anatase.csv`
- expected route: `(none)` (capability missing)
- last observed route verdict: **as_expected**
- last observed selection: `(none)` (confidence 0.0, 0 candidate(s))
- route expectation: This capability is NOT registered in the composed workspace (only EIS, generic input/transform/control nodes and the EBrick case tools are active), so no tool may be selected. Any selection would be a false match.
- why this prompt is long: Full diffractometer report, sample prep, and an explicit judgement criteria request.

Prompt length: 585 characters.

## Input prompt

```text
【样品与制样】样品为实验室自制的 TiO2 粉体，制备方法是钛酸四丁酯水解后 80 °C 干燥，未做进一步煅烧，取约 0.5 g 研磨 10 分钟后压在玻璃样品槽里，表面用载玻片压平，样品厚度约 1 mm。
【仪器与扫描参数】Bruker D8 Advance，Cu Kα 辐射，波长 1.5406 Å，工作电压 40 kV，电流 40 mA，扫描范围 2θ = 10° 到 80°，步长 0.02°，每步停留 0.5 s，采用连续扫描模式。测试环境为室温大气，没有做低背景样品台。
【数据说明】导出的两列数据是 two_theta_deg 和 intensity_counts，已经扣除了仪器本底，但没有做平滑和 Kα2 剥离。数据里在 20° 到 30° 之间有一个很宽的鼓包，可能是无定形相或者玻璃样品槽的贡献，需要你在判断时权衡。
【请求】1) 对这份图谱做峰位提取，报告每个峰的 2θ 位置、相对强度和半高宽。2) 判断主要晶相是锐钛矿还是金红石，或者两者共存，并给出你的判据，特别是用到哪些特征峰、哪些峰是用来区分两者的。3) 明确写出：仅凭这份数据能得出什么结论、不能得出什么结论，例如能否定量两相比例、能否判断晶粒尺寸。
【边界】如果当前工作区没有可用的 XRD 分析工具，请不要用经验规则代替计算，而是直接告诉我缺少什么能力，以及需要人工确认哪些参数。
```
