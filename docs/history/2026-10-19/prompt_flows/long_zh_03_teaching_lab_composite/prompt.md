# Case 16: `long_zh_03_teaching_lab_composite`

- domain: `cross_domain`
- language: `zh`
- intent: `ask_for_clarification`
- expected route: `(none)` (capability missing)
- last observed route verdict: **expected_unsupported**
- last observed selection: `ebrick_cp_g_normalize` (confidence 0.25, 1 candidate(s))
- route expectation: This capability is NOT registered in the composed workspace (only EIS, generic input/transform/control nodes and the EBrick case tools are active), so no tool may be selected. Any selection would be a false match.
- why this prompt is long: A composite of five measurement types described in detail, with no data attached at all.

Prompt length: 614 characters.

## Input prompt

```text
【任务背景】这是本学期仪器分析实验课的结课作业，我做的是一个综合表征实验，同一个样品我做了五种测试，分别是：阻抗谱、X 射线衍射、紫外可见吸收光谱、比重瓶法测密度、以及热重分析。老师要求我们把这五种数据串成一条证据链，说明样品的组成、结构和性能之间的关系。
【样品】样品是自己配的复合粉体，成分是碳酸钙和高分子粘结剂按一定比例混合，具体的质量比我还在确认，因为称量记录还在另一位同学那里。样品大约 20 g，分成了五份分别用于五种测试。
【各项测试的条件我都记得一部分】阻抗谱是在 1 Hz 到 1 MHz 之间测的，振幅 5 mV，温度室温；XRD 扫描 10 到 80 度，铜靶；紫外可见是在 200 到 800 nm 之间扫的，用了积分球附件测固体漫反射；比重瓶用的是去离子水，记录了空瓶、加水、加样品和加样品加水四种质量；热重是从室温升到 900 度，空气气氛，升温速率我不太确定是 10 还是 20 度每分钟。
【我的困难】我上传文件的时候出错了，实验数据一份都没有传上去，只把我整理的这份测试清单发给你了。我自己也不记得最后点的是上传还是提交。
【请求】请你告诉我，在你目前能看到的信息下，可以推进到什么程度；如果我需要重新上传，请一次告诉我每一份数据对应的文件名要求、必需的列名和单位，以及每种测试我需要补充的参数（例如波长、升温速率、标准曲线等）。另外请说明这五种测试之间哪些结论可以互相验证，哪些是彼此独立的。
```
