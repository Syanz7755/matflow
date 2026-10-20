# deepseek-reasoner 补充测量（未完成的 10 条矩阵）

`deepseek-reasoner` 在本窗口可用但极慢：单次调用 8–91 s，单个完整 plan 实测 **402.42 s**。
按同组 10 条提示词运行会超过验收可等待窗口，因此本报告只保留**部分真实记录**，不估算其余条目。

## 已完成的真实记录（1 条）

| 项 | 值 |
|---|---|
| 模型 | SJTU / `deepseek-reasoner` |
| case | `01_eis_basic_qc:canonical_zh`（中文 EIS 基础质检，expected = positive） |
| plan 状态 | `planned`，case_pass = **true**（routing 标签命中） |
| 耗时 | **402.42 s**（单 plan；含多次 LLM 调用） |
| 运行条件 | `--repeats 1 --jev off --workers 2 --per-model 2 --timeout 240`（补充条件，非 mandated flags） |
| 原始记录 | `.tmp/live/matrix/reasoner.checkpoint.jsonl`（本机，未提交） |

## 为什么没有 10 条

- 400 s/plan × 10 条即使并发 2 也需约 35–60 分钟，且会与同期 `deepseek-chat` 矩阵争用同一个 SJTU
  上游，导致整体验收窗口不可控。
- 已完成的 1 条说明**模型可用、routing 正确**，但“10 条完整矩阵”这一项对 reasoner **未达成**；
  这是服务速度限制，不是编造或跳过失败记录。
- 对比：同窗口 `deepseek-official-flash` 的 plan 中位 18.0 s、`deepseek-official-v4-pro` 129.8 s，
  见 [deepseek.md](deepseek.md)；`qwen` 更是退化到 121.7 s/单次调用，同样未计分
  （见 [MATRIX.zhcn.md](MATRIX.zhcn.md)）。
