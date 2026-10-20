# Case 8: `long_dsc_01_transition_enthalpy`

- domain: `dsc`
- language: `zh`
- intent: `routing_only`
- fixture hint: `examples/data/07_dsc_transition_enthalpy/dsc_heating.csv`
- expected route: `(none)` (capability missing)
- last observed route verdict: **expected_unsupported**
- last observed selection: `ebrick_case05_import` (confidence 0.25, 1 candidate(s))
- route expectation: This capability is NOT registered in the composed workspace (only EIS, generic input/transform/control nodes and the EBrick case tools are active), so no tool may be selected. Any selection would be a false match.
- why this prompt is long: Polymorph screening context with a thermal-history argument.
- note: The DSC fixture is a single heating curve; the second polymorph is described but not provided.

Prompt length: 558 characters.

## Input prompt

```text
【背景】我在做药物活性成分的晶型筛选，手上这个化合物已经确认存在两种晶型，晶型 I 是原料，晶型 II 是重结晶得到的，我想用差示扫描量热法确认两者的熔点和熔融焓差异，顺便看看有没有玻璃化转变。
【实验参数】仪器 Mettler Toledo DSC 3，铝制密封坩埚，样品量 4.2 mg，第一次升温从 25 到 250 °C，速率 10 °C/min，氮气保护 50 mL/min，随后以 10 °C/min 降到 -20 °C，再第二次升温到 250 °C 以消除热历史。本次提供的数据只包含第一次升温曲线，两列：temperature_C 和 heat_flow_mW，其中吸热峰朝下为负值。
【数据说明】基线上有一个缓慢的漂移，熔融峰大约在 180 °C 附近，峰形不对称，可能有熔融重结晶。样品在 100 °C 附近有一个很小的台阶，可能是残留溶剂或者玻璃化转变，也可能是水分。
【请求】1) 确定主要热事件的温度：起始点、峰值和结束点，分别说明你用哪种约定。2) 计算熔融焓，单位 J/g，并说明积分区间的选法对结果的影响。3) 判断 100 °C 附近的台阶更像玻璃化转变还是脱水，需要什么额外证据才能区分。4) 明确说明：仅凭第一次升温曲线能否比较两种晶型的稳定性，为什么需要第二次升温或变温循环。
```
