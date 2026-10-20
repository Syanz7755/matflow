# Case 5: `long_ftir_01_functional_groups`

- domain: `ftir`
- language: `zh`
- intent: `routing_only`
- fixture hint: `examples/data/06_ftir_functional_group_assignment/ftir_spectrum.csv`
- expected route: `(none)` (capability missing)
- last observed route verdict: **as_expected**
- last observed selection: `(none)` (confidence 0.0, 0 candidate(s))
- route expectation: This capability is NOT registered in the composed workspace (only EIS, generic input/transform/control nodes and the EBrick case tools are active), so no tool may be selected. Any selection would be a false match.
- why this prompt is long: Realistic FTIR write-up with baseline and atmospheric-absorption caveats.

Prompt length: 636 characters.

## Input prompt

```text
【样品信息】这是我用 KBr 压片法制备的聚合物薄膜样品，样品与 KBr 按大约 1:100 的比例混合研磨，压制成直径 13 mm 的透明片，测试前在红外灯下干燥 20 分钟以除去吸附水。
【采集参数】Thermo Nicolet iS50 傅里叶变换红外光谱仪，分辨率 4 cm-1，扫描次数 32 次，扫描范围 4000 到 400 cm-1，检测器为 DTGS，背景谱在相同条件下采集并已扣除。样品仓没有充氮，所以在 2350 cm-1 附近可能残留 CO2 的双峰，在 667 cm-1 附近也可能有 CO2 弯曲振动，判断时请把这两个位置当作可能的空气峰处理。
【数据说明】导出的两列是 wavenumber_cm-1 和 transmittance_percent，横轴从高波数到低波数递减，透过率基线轻微倾斜，在 3400 cm-1 附近有一个很宽的吸收带，怀疑是羟基或吸附水。
【请求】1) 找出主要的吸收峰位置，并按官能团区域分类：3700-3200、3000-2800、1800-1500、1500-1000、1000-400 五个区间分别列出。2) 对每个区间的峰给出最可能的官能团归属，并说明该归属是强证据还是弱证据，比如是否与其他峰的组合相符。3) 明确指出不能仅凭红外确认的部分，例如取代基位置或交联度。
【约束】不要直接给出最终结构式；这属于需要人工审核的结论。如果现有工具不支持红外峰归属，请说明缺失能力，不要用通用化学知识替代计算流程。
```
