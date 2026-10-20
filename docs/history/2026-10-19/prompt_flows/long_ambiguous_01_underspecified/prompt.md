# Case 10: `long_ambiguous_01_underspecified`

- domain: `cross_domain`
- language: `zh`
- intent: `ask_for_clarification`
- expected route: `(none)` (capability missing)
- last observed route verdict: **as_expected**
- last observed selection: `(none)` (confidence 0.0, 0 candidate(s))
- route expectation: This capability is NOT registered in the composed workspace (only EIS, generic input/transform/control nodes and the EBrick case tools are active), so no tool may be selected. Any selection would be a false match.
- why this prompt is long: A long prompt that nonetheless omits every fact the router needs; it must refuse to guess.

Prompt length: 404 characters.

## Input prompt

```text
老师你好，我这边有个测完的数据想请你帮我处理一下，具体是这样的：上周我在实验室做了表征，仪器是公共平台那台，测试的时候师兄帮我调了参数，我记得好像扫了很多点，数据导出来是一个表格文件，我放在工作目录里了，文件名里带日期，但是我不太确定是哪一个。
我大概记得的数据内容是这样的：第一列好像是自变量，单位可能是度或者纳米或者波数，第二列是信号强度，不过也有可能第一列是时间，因为那台仪器有两种模式。样品是我自己做的，具体成分还在分析，目前只知道里面有金属氧化物，可能是钛也可能是锌，还有一点有机残留。
我想得到的结论是：这个东西到底是什么。最好能告诉我晶体结构、粒径、纯度、还有能不能用作催化剂。如果这些做不到，那就告诉我它是不是无定形的也行。越快越好，我明天要汇报。
另外我上传的时候好像一起传了两个文件，如果不确定用哪个，你就自己挑一个合适的，先用着再说。如果缺少参数，你可以用常规的默认值，我相信你的判断。
```
