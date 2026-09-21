# Jev 回答诊断接入

本次按[分享方案](https://chatgpt.com/s/t_6ab10750b97c8191a7eb03e3acc5f50f)实现回答诊断拆分。主问题、追问生成、评分和报告仍使用现有 DeepSeek 客户端。未修改本机 `.env` 或开启线上 Jev 路由。

## 接口与置信度

HTTP 请求遵循 [TypeSafe 官方接口](https://docs.typesafe.ai/api)，使用 `POST https://api.typesafe.ai/v1/systemone`，Bearer 密钥和 `jev-latest`。使用已有 httpx 依赖，不增加另一套 SDK。一次请求包含相关性 Choice、是否存在可澄清缺口的 Noul、评分点 Choice。上下文仅发送当前题目、rubric 和当前题的问答链。

官方 [confidence 文档](https://docs.typesafe.ai/confidence)明确 Noul 没有 confidence。内部 `followup_confidence` 是相关性和目标 Choice 置信度的最小值，日志标记 `min_relevance_target_choice`。它是本项目的组合保护值，不是 Noul 原生置信度，也没有经过真实面试数据校准。

rubric 每个要点映射为 `point_0`、`point_1` 等稳定的题内标识，另有 `none`。生成追问前查回完整文本。解析器验证类型、概率范围、有限值、分布之和、最大概率选项和准确选项集合；未知目标或缺字段触发回退。

## 流程

`persist_answer → assess_answer → route_assessment`

- 追问次数达到上限：直接评分，不再调用诊断模型。
- Choice 组合置信度低于 0.60：进入显式 `fallback_assessment` 节点。
- Noul 概率 ≥ 0.70 且有合法目标：生成追问。
- Noul 概率 ≤ 0.30：评分。
- 其余概率或高概率但目标为 none：回退。
- Jev 超时、HTTP 错误、网络错误、非法响应或未配置密钥：回退。

回退节点调用原 DeepSeek `AnswerAssessment`，由 `route_fallback_assessment` 路由。DeepSeek 本身失败时继续使用项目现有可恢复错误和 checkpoint 重试机制；不能承诺两个服务都失败时面试仍然继续。

HTTP 操作及整次请求均受超时限制，默认 3 秒，不隐式重试或跟随重定向。客户端由应用生命周期关闭。`JEV_FALLBACK_ENABLED=false` 会将不确定或故障决策变成可恢复错误；生产建议保持 true。

## 配置与启用

配置写在仓库根目录 `.env`，字段模板见 `backend/.env.example`。切换后重启后端使设置生效。

1. 基线：`DECISION_PROVIDER=deepseek`、`JEV_SHADOW_MODE=false`。
2. 对照观察：配置本机 `JEV_API_KEY`，设置 `JEV_SHADOW_MODE=true`。无论 provider 为何，DeepSeek 负责实际路由，Jev 仅记录结果。两者并行执行，但响应仍等待有总超时上限的 Jev 观察结束，可能增加延迟。
3. 正式接管：`DECISION_PROVIDER=jev`、`JEV_SHADOW_MODE=false`、`JEV_FALLBACK_ENABLED=true`。
4. 切回基线：同时恢复第 1 步两项。只切 provider、保留 shadow 时，实际路由也由 DeepSeek 决定，但仍会调用 Jev。

保留 0.70/0.30/0.60 初始阈值；配置验证要求评分阈值小于追问阈值。没有使用合成数据假装已完成阈值调优。

## 日志

`answer_decision` 记录 provider、latency_ms、概率、组合 confidence、目标、route_result、fallback_reason、followup_count，以及会话和题目标识。回退前后的两次判断各有日志。`decision_shadow` 记录 DeepSeek 布尔决策及 Jev 结果、候选路由与原因。日志不记录密钥、完整回答或上游错误正文。

## 测试与评估

在 backend 目录运行 `uv run pytest -q --basetemp <新的可写绝对路径>`。测试使用模型替身与 HTTP MockTransport，不发付费请求；覆盖解析、阈值边界、自定义阈值、超时、回退、Shadow Mode、上限、持久化问答、interrupt 重启恢复及回退节点重试。

`backend/tests/fixtures/decision_cases.json` 包含 56 个助手编写的合成案例：7 个技术主题 × 8 类回答。每条明确标记未经人工审核。数据集用于起步和人工审查，不属于人工金标准或真实用户数据。

验证数据结构：`uv run python -m app.decision.evaluate --validate-only`。

本机配好两个服务的密钥后，可显式运行付费对照：`uv run python -m app.decision.evaluate --output <新的结果文件绝对路径>`。它逐案例调用两家服务，输出逐条结果、直接路由覆盖率、与标签一致率、直接决策一致率、Jev 目标一致率、延迟和回退率。认证失败立即停止。输出路径不得已存在。

灰区和故障不计作 Jev 直接决策的正确答案；报告同时显示覆盖率。DeepSeek 的目标是自由文本，跨供应商目标一致性需要人工审核逐条结果。费用未采集，输出 null 而非虚构的 0。真实费用需结合服务账单；真正的人类标注一致率需先人工审核数据集。使用这批未经审核的数据，不足以支持更低延迟、更低费用或更高准确率的结论。

## 2026-09-21 验证结果

本机配置密钥后，已完成真实 TypeSafe 和 DeepSeek 调用。详细逐条数据见 [56 个案例对照结果](jev-evaluation-2026-09-21.json)。本次运行使用默认 0.70/0.30/0.60 阈值。

| 项目 | 结果 |
| --- | --- |
| 本地回归 | 82 项通过；1 条已有 Starlette/httpx 弃用警告 |
| DeepSeek 诊断成功 | 56/56 |
| Jev 有效诊断 | 55/56 |
| Jev 直接路由 | 23/56（41.1%），全部为追问 |
| 需要 DeepSeek 回退 | 33/56（58.9%） |
| 回退原因 | 低组合置信度 30、概率灰区 2、非法响应 1 |
| 平均单次诊断延迟 | Jev 344 ms；DeepSeek 2189 ms |
| 直接决策与合成标签一致 | 23/23；仅覆盖直接追问子集，不代表整体准确率 |
| 两模型直接决策一致 | 22/23 |

`evaluation_short` 首次触发 `jev_invalid_response`，单独复测成功；未保留原始响应，因此无法确定首次失败的具体字段原因。批量对照结果保留首次失败，没有用重试结果替换。费用未测量，延迟仅是本次合成样本调用的观测值，不是线上 SLA，也未包含后续回退的整条链路耗时。

真实端到端验证使用隔离 SQLite 数据库，走过主问题生成、两次追问、进程重启后继续回答、达到上限后评分落盘、推进下一题和提前结束生成报告。结果为一题已评分、追问数为 2，部分报告包含一条题目回顾。没有改动用户的面试业务数据库。

真实 Shadow Mode 验证中两家服务都返回 200，最终 provider 为 deepseek；Jev 结果仅用于观察。评估工具在首次真实运行中发现合成轮次缺少 `id/kind/followup_level`，已补齐数据契约并增加所有案例经过真实 DeepSeek 提示模板的回归测试。

目前仍保留 `DECISION_PROVIDER=deepseek`、`JEV_SHADOW_MODE=false`，未自动修改本机配置。接入开发和真实服务联调已完成；人工标签审核、真实使用样本积累、费用核算和阈值调优属于后续效果评估，尚无完成证据。建议先用 Shadow Mode 积累真实样本，再决定是否正式切换。
