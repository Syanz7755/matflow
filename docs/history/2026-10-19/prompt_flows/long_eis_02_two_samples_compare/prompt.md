# Case 2: `long_eis_02_two_samples_compare`

- domain: `eis`
- language: `zh`
- intent: `route_then_execute`
- fixture hint: `examples/data/01_eis_basic_qc/eis_spectrum.csv`
- expected route: `eis_basic_qc` (capability registered)
- last observed route verdict: **misrouted**
- last observed selection: `ebrick_case05_import` (confidence 0.5, 5 candidate(s))
- route expectation: A matching tool IS registered and active in this workspace, so the router is expected to select it. If it does not, that is a routing defect this suite is meant to expose.
- why this prompt is long: Two-sample comparison request with a long history and a strict output contract.
- note: Only one fixture is attached for this suite; the second sample is described in prose but not provided.

Prompt length: 466 characters.

## Input prompt

```text
我这一批一共做了两组平行样品，编号 LLZTO-A 和 LLZTO-B，来自同一块烧结片的不同区域，想比较它们的体电阻差异。背景是这样：A 组来自边缘，B 组来自中心，之前 SEM 显示边缘有明显孔洞，我怀疑边缘样品的晶界电阻偏高，但我不敢直接从形貌下结论，所以想先用阻抗谱做一次基础质检，看看两组数据本身是否可靠，再决定要不要做等效电路拟合。
两组数据都是同一台仪器、同一批夹具、同一天测的，温度 25 ± 0.5 °C，开路电压稳定 30 分钟后开始扫频，频率从 1 MHz 降到 0.1 Hz，振幅 10 mV。导出的 CSV 每个文件三列：frequency_Hz、Z_real_ohm、Z_imag_ohm，其中虚部按仪器约定取了负号。
请你先针对我上传的这份数据做基础质量检查并生成 Nyquist 图，把每一步的判断依据写清楚：有效频点数量、是否有离群点、高频截距是多少、低频端是否出现扩散尾巴。然后在最后单独用一小段说明：以现在的数据质量，是否足以支撑“边缘样品晶界电阻更高”这个判断；如果不足，请列出还缺哪些证据。
```
