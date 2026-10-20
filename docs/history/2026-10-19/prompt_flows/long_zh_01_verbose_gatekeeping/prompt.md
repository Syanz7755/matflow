# Case 14: `long_zh_01_verbose_gatekeeping`

- domain: `cross_domain`
- language: `zh`
- intent: `ask_for_clarification`
- expected route: `(none)` (capability missing)
- last observed route verdict: **expected_unsupported**
- last observed selection: `ebrick_cp_g_normalize` (confidence 0.5, 3 candidate(s))
- route expectation: This capability is NOT registered in the composed workspace (only EIS, generic input/transform/control nodes and the EBrick case tools are active), so no tool may be selected. Any selection would be a false match.
- why this prompt is long: Very long prompt whose only real missing fact is which column is which; tests targeted follow-up.

Prompt length: 665 characters.

## Input prompt

```text
【先说明我的情况】我是材料学院研一的学生，第一次独立做电化学测试，很多地方不确定，所以想把我知道的都写下来，麻烦你帮我判断下一步该怎么做。如果我问得不清楚，请直接告诉我缺哪一条信息，不要自己替我做决定。
【样品】我的样品是水热法合成的二氧化锰，洗涤到中性后 80 °C 干燥 12 小时，取 80 mg 和 10 mg 乙炔黑、10 mg PVDF 混合，加 NMP 调成浆料，涂在碳布上，涂覆面积 1 cm2，干燥后活性物质负载量大约 2 mg/cm2。对电极是铂片，参比电极是饱和甘汞电极，电解液是 1 M 硫酸钠。
【测试】我先做了循环伏安，然后做了恒流充放电，最后想做交流阻抗。阻抗谱是在开路电位下测的，频率从 100 kHz 到 0.01 Hz，振幅 5 mV。仪器是上海辰华的，型号我记不清了，可能是 660 或者 760。测试时室温没有精确控制，大概 22 到 25 °C。
【数据】我上传的表格不知道是哪一次导出的，可能是恒流充放电，也可能是阻抗谱。文件的表头是仪器默认生成的英文列名，我看到有 time 和 voltage 两列，也可能有 frequency 那一列，但我打开的时候只扫了一眼。我知道这个描述很含糊，可是我确实不确定，因为我把好几个文件放在同一个文件夹里了。
【想得到的结论】我想知道：1) 我的二氧化锰比电容是多少；2) 电荷转移电阻有多大；3) 能不能判断是赝电容行为还是电池型行为。如果数据不够，请告诉我需要重新测什么。
【提醒】如果我的描述里有自相矛盾的地方，请你指出是哪一处矛盾。谢谢！
```
