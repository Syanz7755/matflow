# Case 9: `long_cross_01_multi_technique`

- domain: `cross_domain`
- language: `zh`
- intent: `routing_only`
- fixture hint: `examples/data/02_xrd_anatase_identification/xrd_anatase.csv`
- expected route: `(none)` (capability missing)
- last observed route verdict: **as_expected**
- last observed selection: `(none)` (confidence 0.0, 0 candidate(s))
- route expectation: This capability is NOT registered in the composed workspace (only EIS, generic input/transform/control nodes and the EBrick case tools are active), so no tool may be selected. Any selection would be a false match.
- why this prompt is long: A multi-technique request that deliberately exceeds any single tool, to test honest scope reporting.

Prompt length: 614 characters.

## Input prompt

```text
【任务概览】我手上有一批同批次的粉体样品，做了 XRD、TGA 和 FTIR 三种表征，想请你帮我建立一条尽量完整的表征链，从相组成到热稳定性再到表面官能团，最后给出一份能写进实验报告的结论清单。我知道这三种数据可能不在同一个时间点采集，请你在结论里把数据来源和时间差异标注清楚。
【样品与制样】样品是溶胶凝胶法制备的 TiO2 复合粉体，掺杂了 3 at% 的氮，前驱体为钛酸四丁酯和尿素，500 °C 煅烧 2 小时。XRD 用 Cu Kα 扫描 10 到 80 度，步长 0.02 度；TGA 从 30 到 900 °C，升温 10 °C/min，空气气氛；FTIR 用 KBr 压片，4000 到 400 cm-1，分辨率 4 cm-1。
【本次提供的数据】我这次只上传了 XRD 那一份两列数据，two_theta_deg 和 intensity_counts。TGA 和 FTIR 的数据我之后再给。
【请求】1) 先说明在当前只有 XRD 数据的前提下，你能完成哪些步骤、不能完成哪些步骤，请把不能做的部分明确列出来，不要用推测填充。2) 对这份 XRD 数据做峰提取和主要晶相判断。3) 给出你建议的后续表征顺序，说明每一步要解决的问题以及为什么需要它。4) 如果需要我补充参数，比如波长、仪器展宽或者样品密度，请一次列全，不要分多轮追问。
【边界】不要跨界使用我没上传的数据；不要把文献经验值当作本次测量结果。
```
