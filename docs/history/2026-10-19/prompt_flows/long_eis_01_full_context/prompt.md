# Case 1: `long_eis_01_full_context`

- domain: `eis`
- language: `zh`
- intent: `route_then_execute`
- fixture hint: `examples/data/01_eis_basic_qc/eis_spectrum.csv`
- expected route: `eis_basic_qc` (capability registered)
- last observed route verdict: **misrouted**
- last observed selection: `ebrick_case05_import` (confidence 0.5, 5 candidate(s))
- route expectation: A matching tool IS registered and active in this workspace, so the router is expected to select it. If it does not, that is a routing defect this suite is meant to expose.
- why this prompt is long: Pastes a full instrument report plus column layout and acceptance criteria.

Prompt length: 595 characters.

## Input prompt

```text
【实验背景】这是一份室温下用辰华 CHI760E 电化学工作站测得的交流阻抗数据，样品是 10 wt% 的 Li7La3Zr2O12 陶瓷片，两面溅射金电极，测试前在 60 °C 真空烘箱中干燥 12 小时。测量参数为：频率范围 1 MHz 到 0.1 Hz，交流振幅 10 mV，直流偏置 0 V，每个十倍频程采集 10 个点，共记录 61 个频点。
【数据说明】导出的 CSV 文件包含三列：第一列 frequency_Hz 是频率，单位赫兹，按从高到低排列；第二列 Z_real_ohm 是阻抗实部；第三列 Z_imag_ohm 是阻抗虚部，负值表示容性响应。原始文件里还有仪器自动写入的表头注释行和一行空行，如果解析出问题请告诉我具体是第几行。
【我需要你做的事情】1) 先对这份阻抗谱做基础质量检查：确认频点是否单调、有没有重复频率、有没有明显的异常点或负的实部，以及高频端是否收敛到纯电阻行为。2) 根据有效数据点生成 Nyquist 图，横轴用阻抗实部，纵轴用负的虚部，两个轴的单位都保持欧姆，图上需要标注高频截距的大致数值。3) 如果质检发现数据不合格，请直接指出是哪几个频点有问题、可能的物理原因是什么，不要跳过问题直接出图。
【约束】请只使用已经注册的工具来完成，不要自己发明新的分析方法；如果某个必需的能力当前不存在，请说明缺失的具体能力，并把待人工确认的部分列出来。
```
