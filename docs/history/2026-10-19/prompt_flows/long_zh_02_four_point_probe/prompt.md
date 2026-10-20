# Case 15: `long_zh_02_four_point_probe`

- domain: `electrical`
- language: `zh`
- intent: `routing_only`
- fixture hint: `examples/data/08_four_point_probe_resistivity/four_point_measurements.csv`
- expected route: `(none)` (capability missing)
- last observed route verdict: **expected_unsupported**
- last observed selection: `ebrick_case05_import` (confidence 0.25, 2 candidate(s))
- route expectation: This capability is NOT registered in the composed workspace (only EIS, generic input/transform/control nodes and the EBrick case tools are active), so no tool may be selected. Any selection would be a false match.
- why this prompt is long: Geometry, correction factors and a thickness dependency spelled out at length.

Prompt length: 627 characters.

## Input prompt

```text
【测量目的】我需要用四探针法测一块半导体薄膜的方块电阻和电阻率，薄膜是磁控溅射生长的 ITO，厚度大约 180 nm，长在玻璃衬底上，样品尺寸 10 mm × 10 mm。
【测量设置】用的是直线四探针，探针间距 1.0 mm，针尖半径大约 40 微米，压力调到刚好接触。电流源是 Keithley 2400，在 1 号针和 4 号针之间注入电流，用 2182A 纳伏表测 2 号和 3 号针之间的电压，电流从 1 微安到 1 毫安取了十个点，每个点正反两个方向各测一次以消除热电势。
【数据说明】导出的 CSV 有五列：current_A 是注入电流，voltage_V 是测量电压，probe_spacing_mm 是探针间距，thickness_nm 是膜厚，position 是样品上的测量位置编号。我在样品中心和四个角附近各测了一组，一共五组，想看看均匀性。
【需要你做的】1) 先做基础质检：判断电流和电压是否线性相关、有没有接触不良导致的跳点、正反方向测量是否一致。2) 计算方块电阻 Rsh，单位欧姆每方，并说明你用的是哪一个几何修正因子，因为薄膜厚度远小于探针间距。3) 换算成电阻率，单位欧姆厘米，并说明膜厚测量误差 5% 对结果的影响有多大。4) 汇总五个位置的结果，判断薄膜的均匀性是否满足一般器件要求，并说明你判断所用的阈值是从哪里来的。
【约束】如果我没有提供衬底类型或者是否需要考虑绝缘衬底修正，请直接问我，不要默认选一个。
```
