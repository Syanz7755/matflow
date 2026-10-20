# Harness 改动与测试记录（2026-10-20 live 验收）

## 改动 1：`examples/evaluate_routing_online.py` 新增 `--cases`

- 新增纯函数 `select_cases(cases, spec) -> (selected, unknown)`：按逗号分隔的 case id 选取，**保持 spec 给出的顺序**，重复 id 只取一次，未知 id 不静默丢弃而是回传。
- `--cases` 出现在 `build_cases` 之后、`--sources/--limit/--sample` 之前；**flag 缺席时走 `select_cases(cases, "")`，返回全部用例，行为与改动前完全一致**。
- 未知 id 的失败先于任何规划执行：打印未知 id 列表 + 匹配数 + 提示（冻结清单 `tests/suites/demo10_routing_cases.json`），退出码 **2**，且不写任何报告文件。
- 报告 `meta.dataset.subset` 记为 `--cases selection of N`，并新增 `meta.dataset.cases_spec`（实际运行的 id 顺序），以便事后核对冻结集与实跑集一致。
- 检查点/实验指纹逻辑未改动：`experiment_fingerprint` 仍对用例、目录、Jev 设置与网关绑定，因此按网关分组的两个检查点不能互相复用。

## 改动 2：`tests/test_routing_online_eval.py` 新增 `CaseSelectionTests`（5 个离线用例，无网络）

| 测试 | 断言 |
|---|---|
| `test_absent_flag_keeps_every_case_unchanged` | `select_cases(cases, "")` 返回全部用例且顺序不变 |
| `test_selection_follows_the_spec_order` | `"c, a"` → 顺序 `c, a`（含空格容错），无 unknown |
| `test_repeated_ids_run_once` | `"b,b,a"` → `b, a` |
| `test_unknown_ids_are_reported_rather_than_ignored` | `"a,nope,other"` → 只选 `a`，unknown 为 `["nope","other"]` |
| `test_frozen_demo10_selection_rebuilds_offline` | 用 `build_cases`（离线）重建冻结文件中的 10 条，逐条比对 `prompt / expect / language / gold.must / gold.forbidden / gold.statuses / fixtures`，并要求无 unknown |

最后一个测试是冻结文件的可复跑守护：一旦上游套件或注册目录变动导致冻结用例漂移，测试会立刻失败，而不是让报告在不知情的情况下引用另一套题。

## 测试结果

```
$ .venv\Scripts\python.exe -V
Python 3.12.13

$ .venv\Scripts\python.exe -m pytest tests/test_routing_online_eval.py -q
........................s                                                [100%]
24 passed, 1 skipped in 0.47s
```

- 24 passed：原有 19 个离线用例（指标、金标签、评分、聚合、隔离、检查点）+ 本轮新增 5 个。
- 1 skipped：`OnlineRoutingSmoke`（未设 `MATFLOW_ONLINE=1`，即本机离线自检不触网）。矩阵实跑本身即在线验证，见 `MATRIX.zhcn.md`。

## 未知 case id 的实际行为（现场核对，退出码 2，不触网跑规划）

```
$ ... evaluate_routing_online.py --models deepseek-chat --repeats 1 --jev off \
    --cases '01_eis_basic_qc:canonical_zh,no_such_case' --out-json .tmp/live/matrix/neg.json
models: ['deepseek-chat']; skipped: {}
Unknown case id(s) in --cases: no_such_case. 1 of the requested ids matched a case; ids come from build_cases (see tests/suites/demo10_routing_cases.json for a frozen example).
exit=2
neg.json exists: False
```

（网关可达时才走到这一步，因此这一条是现场真机核对；离线单元测试覆盖的是同一函数的判定逻辑。）

## 复跑

```powershell
.venv\Scripts\python.exe -m pytest tests/test_routing_online_eval.py -q
```
