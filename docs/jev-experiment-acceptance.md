# Jev 回答诊断改造：实验与验收说明

实验日期：2026-09-21

项目：`D:\Pythoncode\tiemian_agent`

文档性质：依据已保存的对照结果、实现代码及本次会话的验证记录重新整理；本次文档重写没有重新发起付费实验。

## 1. 验收结论

**开发接入与基础联调通过；尚不能据此认定 Jev 已具备全面替代 DeepSeek 回答诊断的效果。**

已验证 Jev 结构化诊断、LangGraph 路由、DeepSeek 回退与追问生成，以及追问上限、状态恢复、评分落盘和部分报告生成。此前最终本地回归为 **82 项通过、1 条已有依赖弃用警告**。

56 个合成案例的真实服务对照中，Jev 有效返回 55 次，直接路由 23 次，其余 33 次按规则需要回退。23 次直接路由全部为“继续追问”。完整回答和追问后补充完整的 14 个案例全部需要回退。因此，本次证据支持“具备可运行的接入和回退机制”，不支持“判断能力全面优于或等同于 DeepSeek”。

建议先用 Shadow Mode 积累经人工审核的真实样本，保留初始阈值，不根据这批合成数据直接放宽门槛。

## 2. 改造范围与职责

| 组件 | 职责 |
| --- | --- |
| Jev | 判断回答相关性、可追问缺口概率，从本题 rubric 中选择追问目标 |
| LangGraph | 根据阈值和追问次数路由，维护状态、interrupt/resume 和显式回退节点 |
| DeepSeek | 基线/回退诊断、主问题与追问生成、题目评分、报告生成 |

本次不替换 DeepSeek 的评分和文本生成能力。接口接入采用 TypeSafe 的 `/v1/systemone`，通过已有 httpx 依赖调用。

代码入口：

- [请求构造与解析](D:/Pythoncode/tiemian_agent/backend/app/decision/assessment.py)
- [诊断客户端](D:/Pythoncode/tiemian_agent/backend/app/decision/client.py)
- [路由规则](D:/Pythoncode/tiemian_agent/backend/app/graph/v1/routing.py)
- [流程节点](D:/Pythoncode/tiemian_agent/backend/app/graph/v1/nodes/interview.py)
- [完整接入说明](D:/Pythoncode/tiemian_agent/docs/jev-decision.md)

## 3. 实验设计

### 3.1 样本与标签

数据集共 56 条，为 **7 个技术主题 × 8 类回答**，由助手编写，标签未经人工审核。

技术主题包括 checkpoint 恢复、RAG 链路、接口幂等、工具调用、召回排查、流式恢复、Agent 评估。回答类别见第 5 节。

每个案例提供题目、rubric、问答轮次、已追问次数，以及预期的追问布尔值和目标。轮次采用项目实际字段：`id`、`role`、`kind`、`followup_level`、`content`。

**这些标签不是人工金标准，样本也不是真实用户数据。** 同一主题内的案例共享题目和评分点，不能将 56 条视为充分独立、具有总体代表性的样本。

数据来源：[decision_cases.json](D:/Pythoncode/tiemian_agent/backend/tests/fixtures/decision_cases.json)。

### 3.2 对照方法

对每个案例，评估工具先调用 DeepSeek 基线诊断，再调用 Jev，分别记录结果和客户端观测耗时。随后用应用的阈值规则计算 Jev 候选路由。

这是一轮逐案例离线对照，**不是线上 A/B 实验**。两家服务都对全部案例尝试诊断；工具没有仅在 Jev 需要回退时再调用 DeepSeek。因此：

- “回退率”是离线结果按规则需要回退的比例。
- 两个平均耗时分别对应单次诊断调用，不是混合系统的端到端耗时。
- 本次没有重复多轮、随机交换调用顺序或测量并发负载，不能给出稳定 SLA 结论。

评估入口：[evaluate.py](D:/Pythoncode/tiemian_agent/backend/app/decision/evaluate.py)。

### 3.3 路由规则

按以下优先级判断：

| 顺序 | 条件 | 动作 |
| --- | --- | --- |
| 1 | 已达追问上限，默认 2 次 | 直接评分，不再调用诊断模型 |
| 2 | Jev 服务失败或响应非法 | DeepSeek 回退 |
| 3 | 组合置信度 < 0.60 | DeepSeek 回退 |
| 4 | 追问概率 ≥ 0.70，且目标合法、非空 | 生成追问 |
| 5 | 追问概率 ≤ 0.30 | 评分 |
| 6 | 概率位于灰区，或高概率但没有追问目标 | DeepSeek 回退 |

Jev 的 Noul 只有概率，不提供独立 confidence。本实现的 `followup_confidence` 是“相关性 Choice 与目标 Choice 的置信度最小值”，日志中标为 `min_relevance_target_choice`。这是项目采用的组合保护值，不是 Noul 原生置信度，尚未经过真实业务数据校准。

## 4. 总体结果

以下数值来自[原始逐条结果](D:/Pythoncode/tiemian_agent/docs/jev-evaluation-2026-09-21.json)，本次重新核对了计数及回退原因。

| 指标 | 结果 | 解释 |
| --- | --- | --- |
| 案例数 | 56 | 合成、未经人工审核 |
| DeepSeek 有效诊断 | 56/56 | 结构化调用成功 |
| Jev 有效诊断 | 55/56 | 1 次响应未通过解析校验 |
| Jev 直接路由覆盖率 | 23/56，41.1% | 全部为追问，直接评分为 0 |
| 按规则需要回退 | 33/56，58.9% | 包括低置信度、灰区和非法响应 |
| DeepSeek 与合成标签一致 | 55/56，98.2% | 不是人类标注准确率 |
| Jev 直接决策与合成标签一致 | 23/23，100% | 仅对直接追问子集计算 |
| 两模型在直接决策子集上一致 | 22/23，95.7% | 不包括回退案例 |
| Jev 目标与合成目标标签一致 | 40/41，97.6% | 仅统计预期追问且 Jev 有效返回的案例 |
| Jev 平均调用耗时 | 344.5 ms | 包含本轮失败尝试的耗时 |
| DeepSeek 平均调用耗时 | 2188.8 ms | 本轮基线诊断耗时 |
| 调用费用 | 未测量 | 结果中的 null 不表示免费或零成本 |

不能将两种单次调用耗时的差额直接视为整体提速；回退分支会叠加两次诊断的等待时间。跨供应商的追问目标一致性也没有自动计算，因为 DeepSeek 返回自由文本目标，需要人工对齐。

## 5. 分类别结果

| 回答类别 | 案例数 | 直接追问 | 直接评分 | 需要回退 |
| --- | ---: | ---: | ---: | ---: |
| 完整回答 | 7 | 0 | 0 | 7 |
| 部分回答 | 7 | 4 | 0 | 3 |
| 简短回答 | 7 | 3 | 0 | 4 |
| 答非所问 | 7 | 6 | 0 | 1 |
| 概念错误 | 7 | 2 | 0 | 5 |
| 缺少工程细节 | 7 | 4 | 0 | 3 |
| 追问后已补充完整 | 7 | 0 | 0 | 7 |
| 多个缺口 | 7 | 4 | 0 | 3 |
| **合计** | **56** | **23** | **0** | **33** |

最需要后续验证的是“不再追问”的识别效果，而不是只提高直接追问覆盖率。当前直接决策子集全部为正例，100% 的子集一致率不能证明模型具备稳定的正负例区分能力。

## 6. 异常记录

| 原因 | 次数 | 处理 |
| --- | ---: | --- |
| `low_confidence` | 30 | 路由到 DeepSeek 回退 |
| `probability_gray_zone` | 2 | 路由到 DeepSeek 回退 |
| `jev_invalid_response` | 1 | 视为诊断服务失败并回退 |

非法响应发生于 `evaluation_short`。会话中单独复测返回有效决策，但首次原始响应未保留，无法确定具体字段原因。原始对照报告保留首次失败，没有用复测结果覆盖。

首次启动对照工具还发现合成轮次缺少 DeepSeek 提示模板要求的字段，失败发生在模型请求之前。已补齐数据契约，并增加全部案例通过实际 DeepSeek 提示模板的回归测试。

## 7. 功能验收矩阵

| 验收项 | 证据类型 | 结论与范围 |
| --- | --- | --- |
| Jev API 接入、真实结构化返回 | 真实服务对照 JSON | 通过；55/56 有效返回 |
| 概率边界、置信度和空目标路由 | 自动测试 | 通过；真实对照未覆盖直接评分成功样本 |
| HTTP 异常、超时、非法响应回退 | MockTransport/模型替身测试 | 通过；不能写成真实服务故障演练 |
| 追问上限与数据库轮次 | 自动测试及真实隔离流程 | 通过；首题追问数为 2 |
| interrupt 与重启恢复 | 自动测试及真实隔离流程 | 通过；重启后继续提交回答 |
| 评分落盘、推进下一题 | 真实隔离数据库 | 通过；首题 SCORED，随后推进第二题 |
| 提前结束与报告生成 | 真实报告文件 | 通过；PARTIAL 报告包含 1 条题目回顾 |
| 五道题完整面试与完整报告 | 自动测试 | 通过；本轮真实服务只验收一题后提前结束 |
| Shadow Mode 由 DeepSeek 控制 | 自动测试及会话中的真实调用输出 | 通过；真实单案例中两服务均返回 200，实际 provider 为 deepseek |
| DeepSeek 配置切换 | 自动测试 | 通过；基线模式不调用 Jev |
| 人工标注准确率、真实场景质量 | 无已完成证据 | 待验收 |
| 费用收益、阈值调优 | 无已完成证据 | 待验收 |

本地测试结果来自本次会话此前的最终测试运行：82 passed，1 warning。警告为 Starlette TestClient 对 httpx 的弃用提示，并非本次诊断逻辑错误。本次重写说明未再次运行测试。

真实隔离验收证据：

- [业务数据库](D:/Pythoncode/tiemian_agent/backend/.pytest_cache/jev-live-pk_9jqi3/business.sqlite3)
- [检查点数据库](D:/Pythoncode/tiemian_agent/backend/.pytest_cache/jev-live-pk_9jqi3/checkpoints.sqlite3)
- [中间快照](D:/Pythoncode/tiemian_agent/backend/.pytest_cache/jev-live-pk_9jqi3/result.json)
- [最终部分报告](D:/Pythoncode/tiemian_agent/backend/.pytest_cache/jev-live-pk_9jqi3/report.json)

本次重新读取数据库确认：第一题为 SCORED、追问数为 2；第二题因提前结束为 ABANDONED。中间快照写于结束前，应以最终数据库和报告判断结束状态。上述证据位于被忽略的测试缓存目录，不是持久归档，清理缓存后可能消失。Shadow Mode 的原始输出保留于会话记录，未独立归档为文件。

## 8. 复现实验

在 PowerShell 中切换至 `D:\Pythoncode\tiemian_agent\backend`。

1. 数据结构检查：执行 `uv run python -m app.decision.evaluate --validate-only`，预期输出 56 条案例及未经人工审核的标签状态。
2. 本地回归：执行 `uv run pytest -q --basetemp <新的可写绝对路径>`。该测试集使用替身和 MockTransport，不调用付费模型。
3. 真实对照：在本机 `D:\Pythoncode\tiemian_agent\.env` 配置密钥后，执行 `uv run python -m app.decision.evaluate --output <新的结果文件绝对路径>`。这一步会调用付费服务，输出路径必须尚不存在。
4. 对照时保持样本与阈值一致，记录模型版本、配置、时间和网络条件，再解释结果差异。现有结果文件没有保存不可变模型版本和完整运行环境快照，不能保证后续逐条复现同样输出。

配置模板：[backend/.env.example](D:/Pythoncode/tiemian_agent/backend/.env.example)。密钥只在本机配置，不应写入实验报告或提交到仓库。

## 9. 启用建议与后续验收

上次联调结束时保留 DeepSeek 基线配置，没有自动启用 Jev 接管。本说明重写未修改任何运行配置，也未重新确认当前运行进程的有效配置。

| 模式 | 配置 | 行为 |
| --- | --- | --- |
| 基线 | `DECISION_PROVIDER=deepseek`，`JEV_SHADOW_MODE=false` | 仅 DeepSeek 诊断 |
| 观察 | `JEV_SHADOW_MODE=true` | DeepSeek 决策；Jev 同步观察并记录 |
| Jev 接管 | `DECISION_PROVIDER=jev`，`JEV_SHADOW_MODE=false`，`JEV_FALLBACK_ENABLED=true` | Jev 优先，不确定或失败时回退 |

配置变更后需要重启后端。Shadow Mode 并行请求两家服务，但仍等待有超时上限的 Jev 观察完成，可能增加延迟。关闭 fallback 会让不确定或服务失败变为可恢复错误，不建议用它作为默认运行方式。

后续应先人工审核案例及目标标签，再积累真实 Shadow Mode 样本；重点补充无需追问、追问后已充分回答、边界模糊和服务故障场景。对端到端延迟、实际账单费用、错误追问与漏追问分别设定验收标准，最后再调整阈值。当前没有预设未经用户确认的上线质量门槛，也没有将这些待办标记为已通过。
