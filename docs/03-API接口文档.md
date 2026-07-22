# 铁面：前后端 API 接口契约

> 文档状态：接口契约基线草案  
> 契约版本：`1.1.0`  
> 基线路径：`/api/v1`  
> 适用范围：MVP 单用户多场文字面试  
> 前置文档：`docs/01-需求文档.md`、`docs/02-架构设计.md`  
> 原则：先契约后编码；前后端不得在未更新本文档的情况下自行改变字段、枚举、事件顺序或错误语义。

## 1. 契约目标与边界

本文档定义 Vue 3 前端与 FastAPI 后端之间的唯一公开契约，覆盖：

- 开始面试页的岗位、侧重点、难度、面试规格、规则与系统就绪状态。
- 历史面试页的完成记录、报告摘要、统计与分页。
- 面试进行页的会话配置、消息、题号、追问层级、问题地图、计时、提交回答、提前结束与失败恢复。
- 面试报告页的完成情况、总分、五个能力维度、总体结论、优势与短板、逐题点评、三条改进建议和下一场推荐。
- LangGraph 每次运行到下一个 `interrupt` 或 `END` 期间的 SSE 事件。

以下内容不通过业务 API 返回：

- 品牌名、首页营销标题、按钮文字、页脚等固定产品文案。
- 微信浅色/深色主题和用户的主题偏好；由前端本地保存。
- 输入框实时字数；由前端根据服务端给出的最大长度本地计算。
- SSE 尚未收到 `question.completed` 的临时 token；它只是展示缓冲，不是业务事实。

### 1.1 已统一的产品口径

1. **评分采用五维正式口径**：`foundation`、`engineering`、`system_design`、`problem_solving`、`communication`。当前静态报告原型的“四维评分”必须在正式前端实现时调整，不能反向改变后端契约。
2. **进度字段拆分**：`current_question_number` 表示当前正在作答的题号，`completed_question_count` 表示已经完成评分的主问题数。前端不得把“当前第 2 题”显示成“已完成 2 题”。
3. **面试中不公开分数**：会话快照和面试 SSE 均不得包含逐题分数、维度分或参考答案；所有评价只在报告可用后返回。
4. **阶段性 POST SSE**：开始、回答、提前结束和重试各建立一次短连接。服务端运行 LangGraph 到下一个 `interrupt` 或 `END`，发送 `stream.done` 后关闭连接。
5. **服务端状态为准**：前端可做展示计算，但不得自行推进题号、增加追问次数、判定完成或计算分数。

## 2. 通用约定

### 2.1 URL、格式与时间

| 项目 | 约定 |
|---|---|
| Base URL | 开发环境示例：`http://127.0.0.1:8000/api/v1` |
| JSON 请求 | `Content-Type: application/json; charset=utf-8` |
| JSON 响应 | `Content-Type: application/json; charset=utf-8` |
| SSE 请求 | `Accept: text/event-stream`，命令体仍为 JSON |
| SSE 响应 | `Content-Type: text/event-stream; charset=utf-8`、`Cache-Control: no-cache, no-transform` |
| 时间 | UTC ISO 8601，例如 `2026-07-21T04:15:18.428Z` |
| 时长 | 接口传整数秒；`31:26` 等展示文本由前端格式化 |
| ID | 不透明字符串；前端不得从前缀、长度或内容推断业务含义 |
| 分数 | 面向用户的分数为 `0`～`100`；证据不足时为 `null`，不得用 `0` 代替 |
| 缓存 | 会话、消息和报告响应统一 `Cache-Control: no-store` |

所有 JSON 字段使用 `snake_case`。响应 schema 中声明为必填的字段即使没有值也应返回 `null`、空数组或空对象，不得在不同状态下随意省略。

### 2.2 统一 JSON 响应结构

成功响应：

```json
{
  "code": "OK",
  "message": "获取成功",
  "data": {
    "request_id": "req_01J2V7F8A6J5K2Q0B4N1E3M9RC"
  }
}
```

失败响应：

```json
{
  "code": "ANSWER_TOO_LONG",
  "message": "回答不能超过 1200 个字符",
  "data": {
    "request_id": "req_01J2V7F8A6J5K2Q0B4N1E3M9RC",
    "recoverable": true,
    "details": [
      {
        "field": "content",
        "reason": "max_length",
        "limit": 1200,
        "actual": 1348
      }
    ]
  }
}
```

约束：

- `code` 是稳定的机器可读码。成功固定为 `OK`；前端分支判断只依赖 `code`，不依赖 `message`。
- `message` 是简短中文说明，可用于兜底提示，但前端可根据 `code` 使用本地化文案。
- `data` 始终是 JSON 对象；失败时至少包含 `request_id`、`recoverable`、`details`。
- HTTP 状态码表达协议结果，业务 `code` 表达具体原因；两者必须同时正确。

### 2.3 幂等、并发与乐观锁

以下 POST 接口必须携带请求头：

```text
Idempotency-Key: 0190f164-2f58-7d9a-a070-2d9b472e5704
```

适用接口：创建会话、开始面试、提交回答、提前结束、重试。约定如下：

1. 同一 `Idempotency-Key`、同一路径和同一请求体重复提交，返回第一次调用的既有结果，不再次推进 LangGraph 或调用 LLM。
2. 同一键配合不同请求体，返回 `IDEMPOTENCY_CONFLICT`。
3. 幂等记录至少保留到该面试会话数据被删除；MVP 不依赖短时内存缓存实现幂等。
4. 状态变更请求携带 `expected_row_version`。服务端成功持久化后递增 `row_version`；版本不匹配返回 `STALE_SESSION_VERSION`。
5. 同一会话同一时刻只允许一个活动图运行；冲突返回 `ACTIVE_OPERATION_EXISTS`，前端随后读取会话快照。
6. 回答还必须携带当前 `interrupt_id` 与 `answer_to_turn_id`，防止旧页面把答案提交到新问题。

### 2.4 会话状态枚举

| 状态 | 含义 | 前端主要行为 |
|---|---|---|
| `CREATED` | 会话已创建，尚未启动 | 可调用开始面试接口 |
| `RUNNING` | 正在出题或执行流程节点 | 展示加载态，禁止重复提交 |
| `WAITING_ANSWER` | LangGraph 已 interrupt，等待回答 | 展示并启用回答框 |
| `EVALUATING` | 正在评估刚提交的回答 | 禁用回答框，等待 SSE |
| `REPORTING` | 正在生成或持久化报告 | 展示报告生成状态 |
| `COMPLETED` | 完整完成并已有完整报告 | 跳转完整报告页 |
| `PARTIAL` | 用户提前结束并已有部分报告 | 跳转部分报告页 |
| `FAILED` | 当前步骤失败且未自动恢复 | 根据 `last_error` 提供重试或结束入口 |

### 2.5 其他稳定枚举

| 字段 | 可选值 |
|---|---|
| `difficulty` | `junior`、`mid`、`senior` |
| `position_code` | MVP 固定为 `ai_agent_development` |
| `focus_code` | `agent_application_engineering`、`rag_knowledge_application`、`workflow_tool_calling` |
| `message.role` | `interviewer`、`candidate` |
| `message.kind` | `main_question`、`followup`、`answer` |
| `question.status` | `planned`、`in_progress`、`completed`、`abandoned` |
| `report.completeness` | `FULL`、`PARTIAL` |
| `finish_reason` | `ALL_QUESTIONS_COMPLETED`、`USER_REQUESTED` |
| `dimension_code` | `foundation`、`engineering`、`system_design`、`problem_solving`、`communication` |

## 3. 核心数据对象

### 3.1 `InterviewProgress`

```json
{
  "current_question_number": 2,
  "total_question_count": 5,
  "completed_question_count": 1,
  "completion_percent": 20,
  "current_followup_count": 1,
  "max_followups_per_question": 2,
  "current_topic_code": "rag_retrieval_diagnosis",
  "current_topic_label": "RAG 召回诊断"
}
```

`completion_percent` 的计算公式固定为：

```text
completed_question_count / total_question_count * 100
```

仅在一道主问题及其追问链完成评分后，`completed_question_count` 才加一。

### 3.2 `InterviewMessage`

```json
{
  "id": "turn_01J2V8B4NQ7PHR9A6D5C3K1MTE",
  "question_id": "qinst_01J2V84S3F7G6Y2K9P5N1ADQRC",
  "role": "interviewer",
  "kind": "followup",
  "followup_level": 1,
  "content": "你提到了用 Recall@K 分段定位。假设向量召回的 Recall@20 正常，但最终 Top-5 的相关性明显下降，你会如何区分是融合策略还是重排模型的问题？",
  "created_at": "2026-07-21T04:15:18.428Z"
}
```

`followup_level` 规则：主问题及其主回答为 `0`；第一次追问及其回答为 `1`；第二次追问及其回答为 `2`。

### 3.3 `QuestionMapItem`

```json
{
  "question_id": "qinst_01J2V84S3F7G6Y2K9P5N1ADQRC",
  "number": 2,
  "topic_code": "rag_retrieval_diagnosis",
  "topic_label": "RAG 召回诊断",
  "status": "in_progress",
  "followup_count": 1,
  "max_followups": 2
}
```

规划中的题目只公开题号和能力主题，不提前公开完整题干；尚未实例化时 `question_id` 为 `null`。

### 3.4 `PendingAnswer`

```json
{
  "interrupt_id": "intr_01J2V8C0T1FVH8M6Z3K9Q5R2AP",
  "answer_to_turn_id": "turn_01J2V8B4NQ7PHR9A6D5C3K1MTE",
  "question_id": "qinst_01J2V84S3F7G6Y2K9P5N1ADQRC",
  "followup_level": 1,
  "min_length": 1,
  "max_length": 1200,
  "placeholder": "组织你的思路并回答追问…"
}
```

只有状态为 `WAITING_ANSWER` 时该对象非空。

### 3.5 `LastError`

```json
{
  "code": "LLM_TIMEOUT",
  "message": "面试官生成超时，可重试当前步骤",
  "recoverable": true,
  "failed_step": "compose_followup",
  "failed_operation_id": "op_answer_01J2V90G5M8Q4R7N1P6K3TACHF",
  "retry_endpoint": "/api/v1/interviews/int_01J2V78H3TZ5N6K1P4Q9R7CMDA/retry/stream",
  "occurred_at": "2026-07-21T04:19:30.000Z"
}
```

会话未失败时 `last_error` 为 `null`。刷新后前端使用该对象恢复错误提示和重试入口，不依赖已经丢失的 SSE `error` 事件。

## 4. 接口总览

| 方法 | 路径 | 响应类型 | 用途 |
|---|---|---|---|
| `GET` | `/interview-options` | JSON | 获取开始页配置、规则与示例题 |
| `GET` | `/health/live` | JSON | 检查 FastAPI 进程存活 |
| `GET` | `/health/ready` | JSON | 检查业务库、checkpoint、题库和模型配置是否就绪 |
| `POST` | `/interviews` | JSON | 创建一场面试会话 |
| `GET` | `/interviews` | JSON | 分页获取已生成报告的历史面试记录 |
| `GET` | `/interviews/{interview_id}` | JSON | 获取权威会话快照，用于进入页面及断流恢复 |
| `POST` | `/interviews/{interview_id}/start/stream` | SSE | 启动流程并流式返回第一道主问题 |
| `POST` | `/interviews/{interview_id}/answers/stream` | SSE | 提交回答并流式返回追问、下一题或结束事件 |
| `POST` | `/interviews/{interview_id}/finish/stream` | SSE | 用户提前结束并生成部分报告 |
| `POST` | `/interviews/{interview_id}/retry/stream` | SSE | 重试当前可恢复失败步骤 |
| `GET` | `/interviews/{interview_id}/report` | JSON | 获取完整或部分评估报告 |

启动、结束和重试是状态机命令，并且需要在同一 HTTP 响应中返回事件流，因此保留显式动作路径；其余接口按资源建模。前端不得另行创造 `/chat`、`/score` 或直连 LLM 的接口。

## 5. JSON 接口

### 5.1 获取面试配置选项

```http
GET /api/v1/interview-options
Accept: application/json
```

请求体：无。

成功响应：`200 OK`

```json
{
  "code": "OK",
  "message": "获取面试配置成功",
  "data": {
    "request_id": "req_01J2V6J2V9G4K7M1F5R3Q8APTC",
    "product": {
      "code": "tiemian",
      "name": "铁面",
      "release_label": "MVP / 01"
    },
    "positions": [
      {
        "code": "ai_agent_development",
        "label": "AI Agent 开发",
        "description": "智能体应用、RAG 与知识应用、工作流与工具调用",
        "focus_options": [
          {
            "code": "agent_application_engineering",
            "label": "Agent 应用工程",
            "short_label": "应用工程"
          },
          {
            "code": "rag_knowledge_application",
            "label": "RAG 与知识应用",
            "short_label": "RAG 知识应用"
          },
          {
            "code": "workflow_tool_calling",
            "label": "工作流与工具调用",
            "short_label": "工具与工作流"
          }
        ]
      }
    ],
    "difficulties": [
      {
        "code": "junior",
        "label": "初级",
        "description": "基础概念"
      },
      {
        "code": "mid",
        "label": "中级",
        "description": "工程实践"
      },
      {
        "code": "senior",
        "label": "高级",
        "description": "系统设计"
      }
    ],
    "defaults": {
      "position_code": "ai_agent_development",
      "focus_code": "agent_application_engineering",
      "difficulty": "mid"
    },
    "interview_spec": {
      "main_question_count": 5,
      "max_followups_per_question": 2,
      "estimated_duration_minutes": 25,
      "feedback_timing": "AFTER_INTERVIEW"
    },
    "rules": {
      "version": "mvp-1",
      "confirmation_required": true,
      "items": [
        "本场包含 5 道主问题，每题最多追问 2 次。",
        "面试过程中不展示分数或参考答案。",
        "完成后生成基于本场回答证据的评估报告。"
      ]
    },
    "preview_question": {
      "topic_label": "RAG 召回诊断",
      "content": "一个 RAG 系统的召回效果突然下降，你会按照什么顺序排查？"
    },
    "usage_disclaimer": "评分仅基于本场回答，用于个人练习，不代表真实录用结果。"
  }
}
```

### 5.2 存活与就绪检查

#### 5.2.1 存活检查

```http
GET /api/v1/health/live
Accept: application/json
```

请求体：无。

成功响应：`200 OK`

```json
{
  "code": "OK",
  "message": "服务存活",
  "data": {
    "request_id": "req_01J2V6PW1M8R0A4K9Q3F7CZ5NE",
    "status": "UP",
    "service": "tiemian-api",
    "api_version": "1.1.0",
    "checked_at": "2026-07-21T03:58:00.000Z"
  }
}
```

#### 5.2.2 就绪检查

```http
GET /api/v1/health/ready
Accept: application/json
```

请求体：无。

成功响应：`200 OK`

```json
{
  "code": "OK",
  "message": "模拟面试系统已就绪",
  "data": {
    "request_id": "req_01J2V6QM4K8D2P9B1N7X5R3CTA",
    "status": "READY",
    "checks": {
      "business_database": "UP",
      "checkpoint_database": "UP",
      "question_bank": "UP",
      "llm_configuration": "UP"
    },
    "checked_at": "2026-07-21T03:58:02.000Z"
  }
}
```

未就绪响应：`503 Service Unavailable`

```json
{
  "code": "SERVICE_NOT_READY",
  "message": "模拟面试系统暂未就绪",
  "data": {
    "request_id": "req_01J2V6R4Q5T8M9H2P1C7N3AXKF",
    "recoverable": true,
    "details": [
      {
        "component": "llm_configuration",
        "reason": "missing_required_environment"
      }
    ]
  }
}
```

该接口只检查配置与必要资源，不发送付费模型请求。

### 5.3 创建面试会话

```http
POST /api/v1/interviews
Content-Type: application/json
Idempotency-Key: 0190f164-2f58-7d9a-a070-2d9b472e5704
```

请求体：

```json
{
  "position_code": "ai_agent_development",
  "focus_code": "rag_knowledge_application",
  "difficulty": "mid",
  "rules_version": "mvp-1",
  "rules_confirmed": true
}
```

成功响应：`201 Created`

```json
{
  "code": "OK",
  "message": "面试会话创建成功",
  "data": {
    "request_id": "req_01J2V77X1CD4F9Z8K6H3N5Q2MT",
    "interview": {
      "id": "int_01J2V78H3TZ5N6K1P4Q9R7CMDA",
      "graph_version": "interview_v1",
      "status": "CREATED",
      "status_label": "等待开始",
      "row_version": 1,
      "config": {
        "position_code": "ai_agent_development",
        "position_label": "AI Agent 开发",
        "focus_code": "rag_knowledge_application",
        "focus_label": "RAG 与知识应用",
        "difficulty": "mid",
        "difficulty_label": "中级"
      },
      "spec": {
        "main_question_count": 5,
        "max_followups_per_question": 2,
        "estimated_duration_minutes": 25
      },
      "rules_version": "mvp-1",
      "progress": {
        "current_question_number": 0,
        "total_question_count": 5,
        "completed_question_count": 0,
        "completion_percent": 0,
        "current_followup_count": 0,
        "max_followups_per_question": 2,
        "current_topic_code": null,
        "current_topic_label": null
      },
      "created_at": "2026-07-21T04:00:00.000Z",
      "started_at": null,
      "completed_at": null
    },
    "links": {
      "self": "/api/v1/interviews/int_01J2V78H3TZ5N6K1P4Q9R7CMDA",
      "start_stream": "/api/v1/interviews/int_01J2V78H3TZ5N6K1P4Q9R7CMDA/start/stream"
    }
  }
}
```

主要失败：`RULES_NOT_CONFIRMED`、`UNSUPPORTED_OPTION`、`IDEMPOTENCY_KEY_REQUIRED`、`IDEMPOTENCY_CONFLICT`、`SERVICE_NOT_READY`。

### 5.4 获取会话快照

```http
GET /api/v1/interviews/int_01J2V78H3TZ5N6K1P4Q9R7CMDA
Accept: application/json
```

请求体：无。

成功响应：`200 OK`

```json
{
  "code": "OK",
  "message": "获取面试会话成功",
  "data": {
    "request_id": "req_01J2V8F9Z0P3T1B7N5K4M6RACQ",
    "interview": {
      "id": "int_01J2V78H3TZ5N6K1P4Q9R7CMDA",
      "graph_version": "interview_v1",
      "status": "WAITING_ANSWER",
      "status_label": "等待回答",
      "row_version": 8,
      "config": {
        "position_code": "ai_agent_development",
        "position_label": "AI Agent 开发",
        "focus_code": "rag_knowledge_application",
        "focus_label": "RAG 与知识应用",
        "difficulty": "mid",
        "difficulty_label": "中级"
      },
      "timing": {
        "started_at": "2026-07-21T04:02:30.000Z",
        "server_time": "2026-07-21T04:15:18.000Z",
        "elapsed_seconds": 768,
        "completed_at": null
      },
      "progress": {
        "current_question_number": 2,
        "total_question_count": 5,
        "completed_question_count": 1,
        "completion_percent": 20,
        "current_followup_count": 1,
        "max_followups_per_question": 2,
        "current_topic_code": "rag_retrieval_diagnosis",
        "current_topic_label": "RAG 召回诊断"
      },
      "current_question": {
        "id": "qinst_01J2V84S3F7G6Y2K9P5N1ADQRC",
        "number": 2,
        "category_code": "rag_knowledge_application",
        "category_label": "RAG 与知识应用",
        "topic_code": "rag_retrieval_diagnosis",
        "topic_label": "RAG 召回诊断",
        "display_title": "RAG 召回诊断",
        "status": "in_progress",
        "followup_count": 1,
        "max_followups": 2
      },
      "messages": [
        {
          "id": "turn_01J2V857P1M4K8C6R9H3N5QTZA",
          "question_id": "qinst_01J2V84S3F7G6Y2K9P5N1ADQRC",
          "role": "interviewer",
          "kind": "main_question",
          "followup_level": 0,
          "content": "你接手了一个已经上线的 RAG 系统，用户最近频繁反馈‘答非所问’。离线抽样发现，相关文档经常没有进入 Top-K。请按优先级说明，你会如何定位召回效果变差的原因？",
          "created_at": "2026-07-21T04:09:00.000Z"
        },
        {
          "id": "turn_01J2V87CP6H9T4M3A8Q1N5RKZF",
          "question_id": "qinst_01J2V84S3F7G6Y2K9P5N1ADQRC",
          "role": "candidate",
          "kind": "answer",
          "followup_level": 0,
          "content": "我会先把链路拆成数据、切分、索引和查询四段。先确认原始文档是否完整入库以及更新时间，再抽样检查 chunk 是否破坏语义；之后用一组标注查询分别观察向量召回和关键词召回的 Recall@K，最后检查 embedding 模型或索引参数最近是否变更。如果单路召回正常，我会继续看融合和重排阶段是否把相关文档挤出了 Top-K。",
          "created_at": "2026-07-21T04:14:00.000Z"
        },
        {
          "id": "turn_01J2V8B4NQ7PHR9A6D5C3K1MTE",
          "question_id": "qinst_01J2V84S3F7G6Y2K9P5N1ADQRC",
          "role": "interviewer",
          "kind": "followup",
          "followup_level": 1,
          "content": "你提到了用 Recall@K 分段定位。假设向量召回的 Recall@20 正常，但最终 Top-5 的相关性明显下降，你会如何区分是融合策略还是重排模型的问题？",
          "created_at": "2026-07-21T04:15:18.428Z"
        }
      ],
      "question_map": [
        {
          "question_id": "qinst_01J2V7ZQ6E3N8C1M5K9R4TPAHF",
          "number": 1,
          "topic_code": "agent_memory",
          "topic_label": "Agent 记忆机制",
          "status": "completed",
          "followup_count": 1,
          "max_followups": 2
        },
        {
          "question_id": "qinst_01J2V84S3F7G6Y2K9P5N1ADQRC",
          "number": 2,
          "topic_code": "rag_retrieval_diagnosis",
          "topic_label": "RAG 召回诊断",
          "status": "in_progress",
          "followup_count": 1,
          "max_followups": 2
        },
        {
          "question_id": null,
          "number": 3,
          "topic_code": "tool_call_reliability",
          "topic_label": "工具调用可靠性",
          "status": "planned",
          "followup_count": 0,
          "max_followups": 2
        },
        {
          "question_id": null,
          "number": 4,
          "topic_code": "workflow_architecture_tradeoff",
          "topic_label": "工作流架构取舍",
          "status": "planned",
          "followup_count": 0,
          "max_followups": 2
        },
        {
          "question_id": null,
          "number": 5,
          "topic_code": "agent_evaluation",
          "topic_label": "Agent 评测体系",
          "status": "planned",
          "followup_count": 0,
          "max_followups": 2
        }
      ],
      "pending_answer": {
        "interrupt_id": "intr_01J2V8C0T1FVH8M6Z3K9Q5R2AP",
        "answer_to_turn_id": "turn_01J2V8B4NQ7PHR9A6D5C3K1MTE",
        "question_id": "qinst_01J2V84S3F7G6Y2K9P5N1ADQRC",
        "followup_level": 1,
        "min_length": 1,
        "max_length": 1200,
        "placeholder": "组织你的思路并回答追问…"
      },
      "score_visibility": "AFTER_INTERVIEW",
      "available_actions": {
        "start": false,
        "submit_answer": true,
        "finish": true,
        "retry": false,
        "view_report": false
      },
      "last_error": null
    }
  }
}
```

该接口是刷新、重新进入页面和 SSE 断流后的权威恢复来源。主要失败：`INTERVIEW_NOT_FOUND`。

### 5.5 获取历史面试记录

```http
GET /api/v1/interviews?page=1&page_size=10
Accept: application/json
```

请求体：无。

查询参数：

| 参数 | 类型 | 默认值 | 约束 | 说明 |
|---|---|---:|---|---|
| `page` | integer | `1` | `>= 1` | 页码，从 1 开始 |
| `page_size` | integer | `10` | `1..50` | 每页记录数 |

成功响应：`200 OK`

```json
{
  "code": "OK",
  "message": "获取历史面试记录成功",
  "data": {
    "request_id": "req_01J2VDA8Q5R3T7M2P9K4NCHFEX",
    "items": [
      {
        "interview_id": "int_01J2V78H3TZ5N6K1P4Q9R7CMDA",
        "status": "COMPLETED",
        "status_label": "已完成",
        "completeness": "FULL",
        "generated_at": "2026-07-21T04:33:56.000Z",
        "completed_at": "2026-07-21T04:33:55.000Z",
        "config": {
          "position_code": "ai_agent_development",
          "position_label": "AI Agent 开发",
          "focus_code": "rag_knowledge_application",
          "focus_label": "RAG 与知识应用",
          "difficulty": "mid",
          "difficulty_label": "中级"
        },
        "completion": {
          "finish_reason": "ALL_QUESTIONS_COMPLETED",
          "completed_question_count": 5,
          "total_question_count": 5,
          "duration_seconds": 1886
        },
        "overall": {
          "total_score": 84,
          "max_score": 100,
          "level_label": "表现良好",
          "expectation_label": "超过本场预期",
          "headline": "你具备扎实的 Agent 工程基础，系统性仍可再进一阶。"
        },
        "report_url": "/api/v1/interviews/int_01J2V78H3TZ5N6K1P4Q9R7CMDA/report"
      },
      {
        "interview_id": "int_01J2V78H3TZ5N6K1P4Q9R7CMDB",
        "status": "PARTIAL",
        "status_label": "已提前结束",
        "completeness": "PARTIAL",
        "generated_at": "2026-07-20T09:12:03.000Z",
        "completed_at": "2026-07-20T09:12:02.000Z",
        "config": {
          "position_code": "ai_agent_development",
          "position_label": "AI Agent 开发",
          "focus_code": "workflow_tool_calling",
          "focus_label": "工作流与工具调用",
          "difficulty": "senior",
          "difficulty_label": "高级"
        },
        "completion": {
          "finish_reason": "USER_REQUESTED",
          "completed_question_count": 2,
          "total_question_count": 5,
          "duration_seconds": 702
        },
        "overall": {
          "total_score": null,
          "max_score": 100,
          "level_label": "暂不评分",
          "expectation_label": "证据不足",
          "headline": "本场已完成内容可用于局部复盘。"
        },
        "report_url": "/api/v1/interviews/int_01J2V78H3TZ5N6K1P4Q9R7CMDB/report"
      }
    ],
    "summary": {
      "total_count": 8,
      "full_count": 6,
      "partial_count": 2
    },
    "pagination": {
      "page": 1,
      "page_size": 10,
      "total_items": 8,
      "total_pages": 1,
      "has_previous": false,
      "has_next": false
    }
  }
}
```

历史列表规则：

- 只返回已经持久化报告且会话状态为 `COMPLETED` 或 `PARTIAL` 的记录；创建中、面试中、失败但未生成报告的会话不得出现。
- 按 `completed_at` 倒序；时间相同时按报告生成时间和会话 ID 倒序，保证分页顺序稳定。
- `overall.total_score` 等评分字段直接读取已保存报告，前端不得重新计算；证据不足时保持 `null`。
- 当前 MVP 没有账号体系，返回当前部署中的全部历史记录。引入多用户后必须增加服务端用户归属过滤，不能依赖前端过滤。
- 具体报告继续通过 `GET /interviews/{interview_id}/report` 获取，列表不内嵌逐题点评和完整证据，避免响应过大。

分页参数非法时返回 `422 VALIDATION_ERROR`。

## 6. SSE 协议与命令接口

### 6.1 SSE 连接模型

前端使用 `fetch` 发起 POST 请求并读取响应流，不使用浏览器原生 `EventSource`，原因是请求必须携带 JSON 命令体和 `Idempotency-Key`。

一个 SSE 命令的生命周期为：

1. 服务端在发送响应头前完成会话、状态、幂等键和请求体校验。
2. 校验失败时返回普通 JSON 错误响应，不建立 SSE。
3. 校验成功后返回 `200 OK` 和 `text/event-stream`，首先发送 `stream.open`。
4. 服务端运行 LangGraph，直到下一个 `interrupt` 或 `END`。
5. 正常结束本次运行时发送 `stream.done`，随后关闭连接。
6. 响应头发出后再发生错误时，HTTP 状态不能改变；服务端发送 `error`，再发送 `stream.done`。

心跳使用 SSE 注释，不属于业务事件：

```text
: ping 2026-07-21T04:15:20.000Z
```

### 6.2 SSE 事件信封

每个事件同时使用 SSE 原生 `id`、`event` 字段和统一的 `code/message/data` JSON 信封：

```text
id: evt_01J2V8D1A2K9M4Q7T5R3C6NPZF
event: question.delta
data: {"code":"OK","message":"问题文本分片","data":{"schema_version":1,"event_id":"evt_01J2V8D1A2K9M4Q7T5R3C6NPZF","event":"question.delta","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_01J2V8CZ7X5Q3N9M1K6R4TBHPA","sequence":4,"occurred_at":"2026-07-21T04:15:18.120Z","payload":{"message_id":"turn_01J2V8B4NQ7PHR9A6D5C3K1MTE","chunk_index":1,"text":"你提到了用 Recall@K 分段定位。"}}}
```

字段约束：

| 字段 | 约束 |
|---|---|
| `schema_version` | 当前固定为整数 `1`；破坏性变化必须递增 |
| `event_id` | 全局唯一，且与 SSE `id:` 完全一致 |
| `event` | 与 SSE `event:` 完全一致 |
| `session_id` | 当前面试会话 ID |
| `operation_id` | 当前一次 POST SSE 命令的执行 ID |
| `sequence` | 在同一 `operation_id` 内从 `1` 开始严格递增 |
| `occurred_at` | UTC ISO 8601 时间 |
| `payload` | 事件专属对象；不得为字符串或数组 |

前端按 `operation_id + sequence` 去重和排序。未知事件应记录并忽略，不得导致整个页面崩溃；不认识的 `schema_version` 必须停止消费并读取会话快照。

### 6.3 事件类型

| 事件 | 发送时机 | `payload` 关键字段 | 前端行为 |
|---|---|---|---|
| `stream.open` | 命令已通过校验 | `command`、`accepted_row_version` | 进入加载态 |
| `answer.accepted` | 用户回答已幂等持久化 | `answer_turn_id`、`question_id`、`followup_level` | 将本地临时回答替换为正式消息 ID |
| `question.changed` | 从上一道主问题进入新的主问题 | `previous_question_id`、`current_question` | 切换当前题和问题地图；追问时不发送 |
| `question.meta` | 确定即将输出的问题元数据 | `message_id`、`kind`、`question_id`、`followup_level` | 创建空的面试官消息气泡 |
| `question.delta` | 模型返回一段题目文本 | `message_id`、`chunk_index`、`text` | 追加到临时气泡 |
| `question.completed` | 完整问题已持久化 | 完整 `message` | 用完整文本覆盖临时缓冲；该事件才是业务事实 |
| `progress.updated` | 题号、完成数或追问层级改变 | 完整 `progress`、`row_version` | 整体替换右侧进度数据 |
| `waiting.answer` | LangGraph 到达 `interrupt` | 完整 `pending_answer`、`row_version` | 启用回答框 |
| `report.delta` | 报告文字正在生成 | `section`、`chunk_index`、`text` | 可展示生成进度，不写入正式报告状态 |
| `report.completed` | 报告已完整持久化 | `report_id`、`completeness`、`report_url` | 标记报告可读取 |
| `interview.completed` | 会话进入 `COMPLETED` 或 `PARTIAL` | `status`、`finish_reason`、完成数 | 跳转报告页或显示完成状态 |
| `error` | 建立 SSE 后当前步骤失败 | `error_code`、`recoverable`、`retry_endpoint` | 显示错误并按规则恢复 |
| `stream.done` | 本次图运行结束 | `reason`、`final_status`、`row_version` | 结束读取并退出加载态 |

事件中不得下发任何尚未公开的逐题评分、维度评分、评分证据或参考答案。

### 6.4 启动面试并获取第一题

```http
POST /api/v1/interviews/int_01J2V78H3TZ5N6K1P4Q9R7CMDA/start/stream
Content-Type: application/json
Accept: text/event-stream
Idempotency-Key: 0190f19b-67a2-7d39-b4a5-c82ef395dc12
```

请求体：

```json
{
  "expected_row_version": 1
}
```

成功响应：`200 OK`，完整事件顺序示例：

```text
id: evt_start_001
event: stream.open
data: {"code":"OK","message":"开始面试请求已接受","data":{"schema_version":1,"event_id":"evt_start_001","event":"stream.open","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_start_01J2V7B2M8P5K1T9Q4N6R3CAHF","sequence":1,"occurred_at":"2026-07-21T04:02:30.000Z","payload":{"command":"START_INTERVIEW","accepted_row_version":1}}}

id: evt_start_002
event: question.changed
data: {"code":"OK","message":"进入第 1 道主问题","data":{"schema_version":1,"event_id":"evt_start_002","event":"question.changed","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_start_01J2V7B2M8P5K1T9Q4N6R3CAHF","sequence":2,"occurred_at":"2026-07-21T04:02:30.100Z","payload":{"previous_question_id":null,"current_question":{"id":"qinst_01J2V7ZQ6E3N8C1M5K9R4TPAHF","number":1,"topic_code":"agent_memory","topic_label":"Agent 记忆机制","display_title":"Agent 记忆机制","status":"in_progress","followup_count":0,"max_followups":2}}}}

id: evt_start_003
event: question.meta
data: {"code":"OK","message":"主问题元数据已生成","data":{"schema_version":1,"event_id":"evt_start_003","event":"question.meta","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_start_01J2V7B2M8P5K1T9Q4N6R3CAHF","sequence":3,"occurred_at":"2026-07-21T04:02:30.150Z","payload":{"message_id":"turn_01J2V7ZV2B8R6K5P1N4M9QCHTA","question_id":"qinst_01J2V7ZQ6E3N8C1M5K9R4TPAHF","kind":"main_question","followup_level":0}}}

id: evt_start_004
event: question.delta
data: {"code":"OK","message":"问题文本分片","data":{"schema_version":1,"event_id":"evt_start_004","event":"question.delta","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_start_01J2V7B2M8P5K1T9Q4N6R3CAHF","sequence":4,"occurred_at":"2026-07-21T04:02:30.420Z","payload":{"message_id":"turn_01J2V7ZV2B8R6K5P1N4M9QCHTA","chunk_index":0,"text":"请为一个需要连续多轮执行任务的 Agent "}}}

id: evt_start_005
event: question.delta
data: {"code":"OK","message":"问题文本分片","data":{"schema_version":1,"event_id":"evt_start_005","event":"question.delta","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_start_01J2V7B2M8P5K1T9Q4N6R3CAHF","sequence":5,"occurred_at":"2026-07-21T04:02:30.560Z","payload":{"message_id":"turn_01J2V7ZV2B8R6K5P1N4M9QCHTA","chunk_index":1,"text":"设计短期记忆与长期记忆，并说明写入、检索和过期策略。"}}}

id: evt_start_006
event: question.completed
data: {"code":"OK","message":"主问题已生成","data":{"schema_version":1,"event_id":"evt_start_006","event":"question.completed","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_start_01J2V7B2M8P5K1T9Q4N6R3CAHF","sequence":6,"occurred_at":"2026-07-21T04:02:30.620Z","payload":{"message":{"id":"turn_01J2V7ZV2B8R6K5P1N4M9QCHTA","question_id":"qinst_01J2V7ZQ6E3N8C1M5K9R4TPAHF","role":"interviewer","kind":"main_question","followup_level":0,"content":"请为一个需要连续多轮执行任务的 Agent 设计短期记忆与长期记忆，并说明写入、检索和过期策略。","created_at":"2026-07-21T04:02:30.600Z"}}}}

id: evt_start_007
event: progress.updated
data: {"code":"OK","message":"面试进度已更新","data":{"schema_version":1,"event_id":"evt_start_007","event":"progress.updated","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_start_01J2V7B2M8P5K1T9Q4N6R3CAHF","sequence":7,"occurred_at":"2026-07-21T04:02:30.650Z","payload":{"row_version":3,"progress":{"current_question_number":1,"total_question_count":5,"completed_question_count":0,"completion_percent":0,"current_followup_count":0,"max_followups_per_question":2,"current_topic_code":"agent_memory","current_topic_label":"Agent 记忆机制"}}}}

id: evt_start_008
event: waiting.answer
data: {"code":"OK","message":"等待用户回答","data":{"schema_version":1,"event_id":"evt_start_008","event":"waiting.answer","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_start_01J2V7B2M8P5K1T9Q4N6R3CAHF","sequence":8,"occurred_at":"2026-07-21T04:02:30.700Z","payload":{"row_version":3,"pending_answer":{"interrupt_id":"intr_01J2V801D4M9Q6R7N2K5T3ACPH","answer_to_turn_id":"turn_01J2V7ZV2B8R6K5P1N4M9QCHTA","question_id":"qinst_01J2V7ZQ6E3N8C1M5K9R4TPAHF","followup_level":0,"min_length":1,"max_length":1200,"placeholder":"组织你的思路并回答问题…"}}}}

id: evt_start_009
event: stream.done
data: {"code":"OK","message":"本次事件流已结束","data":{"schema_version":1,"event_id":"evt_start_009","event":"stream.done","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_start_01J2V7B2M8P5K1T9Q4N6R3CAHF","sequence":9,"occurred_at":"2026-07-21T04:02:30.720Z","payload":{"reason":"WAITING_ANSWER","final_status":"WAITING_ANSWER","row_version":3,"snapshot_url":"/api/v1/interviews/int_01J2V78H3TZ5N6K1P4Q9R7CMDA","report_url":null}}}
```

主要失败：`INTERVIEW_NOT_FOUND`、`INTERVIEW_ALREADY_STARTED`、`STALE_SESSION_VERSION`、`ACTIVE_OPERATION_EXISTS`、`QUESTION_GENERATION_FAILED`。

### 6.5 提交回答并获取追问、下一题或结束事件

```http
POST /api/v1/interviews/int_01J2V78H3TZ5N6K1P4Q9R7CMDA/answers/stream
Content-Type: application/json
Accept: text/event-stream
Idempotency-Key: 0190f1b2-5b96-73d1-93f8-2a7b91c2bbd4
```

请求体：

```json
{
  "interrupt_id": "intr_01J2V801D4M9Q6R7N2K5T3ACPH",
  "answer_to_turn_id": "turn_01J2V7ZV2B8R6K5P1N4M9QCHTA",
  "content": "短期记忆放当前任务所需的最近消息、工具结果和阶段状态，超过上下文预算后做结构化摘要。长期记忆只写入可复用且经过验证的信息，按用户和任务隔离，并设置敏感信息过滤、置信度与过期时间。检索时根据任务意图做混合召回和重排，写入前先去重，最后用任务成功率和错误引用率评估记忆是否有效。",
  "expected_row_version": 3
}
```

以下示例表示服务端决定进行第一次追问：

```text
id: evt_answer_001
event: stream.open
data: {"code":"OK","message":"提交回答请求已接受","data":{"schema_version":1,"event_id":"evt_answer_001","event":"stream.open","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_answer_01J2V81D9M6K4R7Q2T5N3ACHFP","sequence":1,"occurred_at":"2026-07-21T04:05:10.000Z","payload":{"command":"SUBMIT_ANSWER","accepted_row_version":3}}}

id: evt_answer_002
event: answer.accepted
data: {"code":"OK","message":"回答已保存","data":{"schema_version":1,"event_id":"evt_answer_002","event":"answer.accepted","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_answer_01J2V81D9M6K4R7Q2T5N3ACHFP","sequence":2,"occurred_at":"2026-07-21T04:05:10.080Z","payload":{"answer_turn_id":"turn_01J2V81G8N5P3Q9M2K7R4TACHF","question_id":"qinst_01J2V7ZQ6E3N8C1M5K9R4TPAHF","followup_level":0,"created_at":"2026-07-21T04:05:10.060Z"}}}

id: evt_answer_003
event: question.meta
data: {"code":"OK","message":"追问元数据已生成","data":{"schema_version":1,"event_id":"evt_answer_003","event":"question.meta","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_answer_01J2V81D9M6K4R7Q2T5N3ACHFP","sequence":3,"occurred_at":"2026-07-21T04:05:11.000Z","payload":{"message_id":"turn_01J2V82A4T7N9P5M1Q6K3RCHFD","question_id":"qinst_01J2V7ZQ6E3N8C1M5K9R4TPAHF","kind":"followup","followup_level":1}}}

id: evt_answer_004
event: question.delta
data: {"code":"OK","message":"问题文本分片","data":{"schema_version":1,"event_id":"evt_answer_004","event":"question.delta","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_answer_01J2V81D9M6K4R7Q2T5N3ACHFP","sequence":4,"occurred_at":"2026-07-21T04:05:11.120Z","payload":{"message_id":"turn_01J2V82A4T7N9P5M1Q6K3RCHFD","chunk_index":0,"text":"如果一条长期记忆后来被证实已经过时，"}}}

id: evt_answer_005
event: question.delta
data: {"code":"OK","message":"问题文本分片","data":{"schema_version":1,"event_id":"evt_answer_005","event":"question.delta","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_answer_01J2V81D9M6K4R7Q2T5N3ACHFP","sequence":5,"occurred_at":"2026-07-21T04:05:11.260Z","payload":{"message_id":"turn_01J2V82A4T7N9P5M1Q6K3RCHFD","chunk_index":1,"text":"你会如何避免它继续影响 Agent 的后续决策？"}}}

id: evt_answer_006
event: question.completed
data: {"code":"OK","message":"追问已生成","data":{"schema_version":1,"event_id":"evt_answer_006","event":"question.completed","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_answer_01J2V81D9M6K4R7Q2T5N3ACHFP","sequence":6,"occurred_at":"2026-07-21T04:05:11.320Z","payload":{"message":{"id":"turn_01J2V82A4T7N9P5M1Q6K3RCHFD","question_id":"qinst_01J2V7ZQ6E3N8C1M5K9R4TPAHF","role":"interviewer","kind":"followup","followup_level":1,"content":"如果一条长期记忆后来被证实已经过时，你会如何避免它继续影响 Agent 的后续决策？","created_at":"2026-07-21T04:05:11.300Z"}}}}

id: evt_answer_007
event: progress.updated
data: {"code":"OK","message":"追问进度已更新","data":{"schema_version":1,"event_id":"evt_answer_007","event":"progress.updated","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_answer_01J2V81D9M6K4R7Q2T5N3ACHFP","sequence":7,"occurred_at":"2026-07-21T04:05:11.350Z","payload":{"row_version":5,"progress":{"current_question_number":1,"total_question_count":5,"completed_question_count":0,"completion_percent":0,"current_followup_count":1,"max_followups_per_question":2,"current_topic_code":"agent_memory","current_topic_label":"Agent 记忆机制"}}}}

id: evt_answer_008
event: waiting.answer
data: {"code":"OK","message":"等待用户回答追问","data":{"schema_version":1,"event_id":"evt_answer_008","event":"waiting.answer","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_answer_01J2V81D9M6K4R7Q2T5N3ACHFP","sequence":8,"occurred_at":"2026-07-21T04:05:11.380Z","payload":{"row_version":5,"pending_answer":{"interrupt_id":"intr_01J2V82B5M4N8Q7R1P6K3TACHF","answer_to_turn_id":"turn_01J2V82A4T7N9P5M1Q6K3RCHFD","question_id":"qinst_01J2V7ZQ6E3N8C1M5K9R4TPAHF","followup_level":1,"min_length":1,"max_length":1200,"placeholder":"组织你的思路并回答追问…"}}}}

id: evt_answer_009
event: stream.done
data: {"code":"OK","message":"本次事件流已结束","data":{"schema_version":1,"event_id":"evt_answer_009","event":"stream.done","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_answer_01J2V81D9M6K4R7Q2T5N3ACHFP","sequence":9,"occurred_at":"2026-07-21T04:05:11.400Z","payload":{"reason":"WAITING_ANSWER","final_status":"WAITING_ANSWER","row_version":5,"snapshot_url":"/api/v1/interviews/int_01J2V78H3TZ5N6K1P4Q9R7CMDA","report_url":null}}}
```

其他合法分支：

| 判断结果 | 事件差异 |
|---|---|
| 进入下一道主问题 | `answer.accepted` 后发送 `question.changed`，再发送新主问题的 `question.meta`、`question.delta`、`question.completed` |
| 完成第 5 题 | 不再发送问题事件；依次发送 `report.delta`、`report.completed`、`interview.completed`、`stream.done` |
| 达到第 2 次追问上限 | 服务端强制完成本题；进入下一题或完成整场，不允许第 3 次追问 |
| 回答无效 | 在建立 SSE 前返回普通 JSON `ANSWER_EMPTY` 或 `ANSWER_TOO_LONG`；不增加追问次数 |

主要失败：`INTERVIEW_NOT_FOUND`、`INVALID_INTERVIEW_STATE`、`STALE_INTERRUPT`、`STALE_SESSION_VERSION`、`ANSWER_EMPTY`、`ANSWER_TOO_LONG`、`ACTIVE_OPERATION_EXISTS`、`ASSESSMENT_FAILED`。

### 6.6 提前结束并生成部分报告

前端必须先展示二次确认，并明确报告只基于已完成主问题生成。确认后调用：

```http
POST /api/v1/interviews/int_01J2V78H3TZ5N6K1P4Q9R7CMDA/finish/stream
Content-Type: application/json
Accept: text/event-stream
Idempotency-Key: 0190f1d7-6e4c-7a52-b178-3f49a7f72cc1
```

请求体：

```json
{
  "reason": "USER_REQUESTED",
  "confirm_partial_report": true,
  "expected_row_version": 8
}
```

成功响应：`200 OK`

```text
id: evt_finish_001
event: stream.open
data: {"code":"OK","message":"提前结束请求已接受","data":{"schema_version":1,"event_id":"evt_finish_001","event":"stream.open","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_finish_01J2V8K1M4Q9T7R2N6P3ACHFZD","sequence":1,"occurred_at":"2026-07-21T04:16:00.000Z","payload":{"command":"FINISH_INTERVIEW","accepted_row_version":8}}}

id: evt_finish_002
event: report.delta
data: {"code":"OK","message":"报告文本分片","data":{"schema_version":1,"event_id":"evt_finish_002","event":"report.delta","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_finish_01J2V8K1M4Q9T7R2N6P3ACHFZD","sequence":2,"occurred_at":"2026-07-21T04:16:01.200Z","payload":{"section":"summary","chunk_index":0,"text":"你已完成 1 道主问题，当前证据显示你能结构化拆解 Agent 记忆机制，"}}}

id: evt_finish_003
event: report.delta
data: {"code":"OK","message":"报告文本分片","data":{"schema_version":1,"event_id":"evt_finish_003","event":"report.delta","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_finish_01J2V8K1M4Q9T7R2N6P3ACHFZD","sequence":3,"occurred_at":"2026-07-21T04:16:01.350Z","payload":{"section":"summary","chunk_index":1,"text":"但样本不足，无法形成完整的五维能力结论。"}}}

id: evt_finish_004
event: report.completed
data: {"code":"OK","message":"部分报告已生成","data":{"schema_version":1,"event_id":"evt_finish_004","event":"report.completed","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_finish_01J2V8K1M4Q9T7R2N6P3ACHFZD","sequence":4,"occurred_at":"2026-07-21T04:16:02.000Z","payload":{"report_id":"rpt_01J2V8M2Q7P4N9K3T5R1ACHFZD","completeness":"PARTIAL","report_url":"/api/v1/interviews/int_01J2V78H3TZ5N6K1P4Q9R7CMDA/report"}}}

id: evt_finish_005
event: interview.completed
data: {"code":"OK","message":"面试已提前结束","data":{"schema_version":1,"event_id":"evt_finish_005","event":"interview.completed","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_finish_01J2V8K1M4Q9T7R2N6P3ACHFZD","sequence":5,"occurred_at":"2026-07-21T04:16:02.050Z","payload":{"status":"PARTIAL","finish_reason":"USER_REQUESTED","completed_question_count":1,"total_question_count":5,"completed_at":"2026-07-21T04:16:02.000Z"}}}

id: evt_finish_006
event: stream.done
data: {"code":"OK","message":"本次事件流已结束","data":{"schema_version":1,"event_id":"evt_finish_006","event":"stream.done","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_finish_01J2V8K1M4Q9T7R2N6P3ACHFZD","sequence":6,"occurred_at":"2026-07-21T04:16:02.080Z","payload":{"reason":"PARTIAL_REPORT_READY","final_status":"PARTIAL","row_version":10,"snapshot_url":"/api/v1/interviews/int_01J2V78H3TZ5N6K1P4Q9R7CMDA","report_url":"/api/v1/interviews/int_01J2V78H3TZ5N6K1P4Q9R7CMDA/report"}}}
```

已进入 `COMPLETED` 或 `PARTIAL` 的会话再次结束时，使用同一幂等键返回既有结果；使用新键时返回当前最终快照，不重新生成报告。未确认部分报告返回 `PARTIAL_REPORT_NOT_CONFIRMED`。

### 6.7 重试失败步骤

只有会话快照中 `available_actions.retry = true` 时才能调用。

```http
POST /api/v1/interviews/int_01J2V78H3TZ5N6K1P4Q9R7CMDA/retry/stream
Content-Type: application/json
Accept: text/event-stream
Idempotency-Key: 0190f1ea-f2ec-716b-a55e-b7e516ef7d48
```

请求体：

```json
{
  "failed_operation_id": "op_answer_01J2V90G5M8Q4R7N1P6K3TACHF",
  "expected_row_version": 9
}
```

成功响应示例表示重试后恢复到等待回答：

```text
id: evt_retry_001
event: stream.open
data: {"code":"OK","message":"重试请求已接受","data":{"schema_version":1,"event_id":"evt_retry_001","event":"stream.open","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_retry_01J2V91N8Q5R3T7M2P6K4ACHFZ","sequence":1,"occurred_at":"2026-07-21T04:20:00.000Z","payload":{"command":"RETRY_FAILED_STEP","accepted_row_version":9,"failed_operation_id":"op_answer_01J2V90G5M8Q4R7N1P6K3TACHF"}}}

id: evt_retry_002
event: question.completed
data: {"code":"OK","message":"问题生成已恢复","data":{"schema_version":1,"event_id":"evt_retry_002","event":"question.completed","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_retry_01J2V91N8Q5R3T7M2P6K4ACHFZ","sequence":2,"occurred_at":"2026-07-21T04:20:01.000Z","payload":{"message":{"id":"turn_01J2V91Q4T7M9P5N2K6R3ACHFD","question_id":"qinst_01J2V84S3F7G6Y2K9P5N1ADQRC","role":"interviewer","kind":"followup","followup_level":1,"content":"如果重排模型离线指标正常，但线上 Top-5 仍明显下降，你会优先验证哪些线上差异？","created_at":"2026-07-21T04:20:00.980Z"}}}}

id: evt_retry_003
event: waiting.answer
data: {"code":"OK","message":"等待用户回答","data":{"schema_version":1,"event_id":"evt_retry_003","event":"waiting.answer","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_retry_01J2V91N8Q5R3T7M2P6K4ACHFZ","sequence":3,"occurred_at":"2026-07-21T04:20:01.050Z","payload":{"row_version":11,"pending_answer":{"interrupt_id":"intr_01J2V91S6M4N8Q7R1P5K3TACHF","answer_to_turn_id":"turn_01J2V91Q4T7M9P5N2K6R3ACHFD","question_id":"qinst_01J2V84S3F7G6Y2K9P5N1ADQRC","followup_level":1,"min_length":1,"max_length":1200,"placeholder":"组织你的思路并回答追问…"}}}}

id: evt_retry_004
event: stream.done
data: {"code":"OK","message":"本次事件流已结束","data":{"schema_version":1,"event_id":"evt_retry_004","event":"stream.done","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_retry_01J2V91N8Q5R3T7M2P6K4ACHFZ","sequence":4,"occurred_at":"2026-07-21T04:20:01.080Z","payload":{"reason":"WAITING_ANSWER","final_status":"WAITING_ANSWER","row_version":11,"snapshot_url":"/api/v1/interviews/int_01J2V78H3TZ5N6K1P4Q9R7CMDA","report_url":null}}}
```

若失败发生在评分或报告节点，重试事件可以不包含问题事件，但必须最终发送 `progress.updated`、`report.completed`、`waiting.answer` 或 `interview.completed` 中至少一个可确定页面状态的事件。

### 6.8 SSE 内错误示例

SSE 已建立后，如果 DeepSeek 超时且自动重试仍失败：

```text
id: evt_error_007
event: error
data: {"code":"LLM_TIMEOUT","message":"面试官生成超时，可重试当前步骤","data":{"schema_version":1,"event_id":"evt_error_007","event":"error","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_answer_01J2V90G5M8Q4R7N1P6K3TACHF","sequence":7,"occurred_at":"2026-07-21T04:19:30.000Z","payload":{"error_code":"LLM_TIMEOUT","recoverable":true,"failed_step":"compose_followup","failed_operation_id":"op_answer_01J2V90G5M8Q4R7N1P6K3TACHF","retry_endpoint":"/api/v1/interviews/int_01J2V78H3TZ5N6K1P4Q9R7CMDA/retry/stream","snapshot_url":"/api/v1/interviews/int_01J2V78H3TZ5N6K1P4Q9R7CMDA"}}}

id: evt_error_008
event: stream.done
data: {"code":"OK","message":"本次事件流因可恢复错误结束","data":{"schema_version":1,"event_id":"evt_error_008","event":"stream.done","session_id":"int_01J2V78H3TZ5N6K1P4Q9R7CMDA","operation_id":"op_answer_01J2V90G5M8Q4R7N1P6K3TACHF","sequence":8,"occurred_at":"2026-07-21T04:19:30.020Z","payload":{"reason":"RECOVERABLE_ERROR","final_status":"FAILED","row_version":9,"snapshot_url":"/api/v1/interviews/int_01J2V78H3TZ5N6K1P4Q9R7CMDA","report_url":null}}}
```

### 6.9 断流恢复

前端未收到 `stream.done` 就发生网络断开时，执行以下固定流程：

1. 停止加载动画，保留用户已经提交的本地文本，但丢弃未收到 `question.completed` 的问题 token 缓冲。
2. 调用 `GET /interviews/{interview_id}`。
3. 若快照为 `WAITING_ANSWER`，用 `messages` 和 `pending_answer` 完整重建页面，不重放旧 token。
4. 若快照仍为 `RUNNING`、`EVALUATING` 或 `REPORTING`，使用原 `Idempotency-Key` 重试原命令；服务端返回既有结果或继续未完成步骤。
5. 若快照为 `FAILED` 且 `available_actions.retry = true`，显示重试入口。
6. 若快照为 `COMPLETED` 或 `PARTIAL`，直接读取报告。

MVP 不实现基于 `Last-Event-ID` 的跨连接 token 回放。原因是最终问题和报告均已持久化，快照恢复比重放临时 token 更可靠。

## 7. 获取面试报告

```http
GET /api/v1/interviews/int_01J2V78H3TZ5N6K1P4Q9R7CMDA/report
Accept: application/json
```

请求体：无。

成功响应：`200 OK`

```json
{
  "code": "OK",
  "message": "获取面试报告成功",
  "data": {
    "request_id": "req_01J2VD7N4M9Q2T6R1P5K3ACHFZ",
    "report": {
      "id": "rpt_01J2VD6A8Q5R3T7M2P9K4NCHFE",
      "interview_id": "int_01J2V78H3TZ5N6K1P4Q9R7CMDA",
      "completeness": "FULL",
      "generated_at": "2026-07-21T04:33:56.000Z",
      "config": {
        "position_code": "ai_agent_development",
        "position_label": "AI Agent 开发",
        "focus_code": "rag_knowledge_application",
        "focus_label": "RAG 与知识应用",
        "difficulty": "mid",
        "difficulty_label": "中级"
      },
      "completion": {
        "finish_reason": "ALL_QUESTIONS_COMPLETED",
        "completed_question_count": 5,
        "total_question_count": 5,
        "duration_seconds": 1886,
        "evidence_status": "SUFFICIENT",
        "limitation_note": null
      },
      "overall": {
        "total_score": 84,
        "max_score": 100,
        "level_code": "GOOD",
        "level_label": "表现良好",
        "expectation_code": "ABOVE_EXPECTATION",
        "expectation_label": "超过本场预期",
        "headline": "你具备扎实的 Agent 工程基础，系统性仍可再进一阶。",
        "summary": "你能快速拆解问题并给出可落地的排查路径，在 RAG 诊断和工具调用方面表现突出。进一步加强评测闭环与边界条件的量化，会让答案更接近高级工程师水位。"
      },
      "score_scale": [
        {
          "code": "NEEDS_IMPROVEMENT",
          "label": "需加强",
          "min_inclusive": 0,
          "max_inclusive": 59
        },
        {
          "code": "MEETS_EXPECTATION",
          "label": "达到预期",
          "min_inclusive": 60,
          "max_inclusive": 84
        },
        {
          "code": "EXCELLENT",
          "label": "优秀",
          "min_inclusive": 85,
          "max_inclusive": 100
        }
      ],
      "dimensions": [
        {
          "code": "foundation",
          "label": "基础知识准确性",
          "short_label": "基础知识",
          "weight": 0.2,
          "score": 88,
          "max_score": 100,
          "level_code": "STRENGTH",
          "level_label": "优势项",
          "summary": "核心概念准确，能清楚区分检索、重排与生成阶段。",
          "evidence_status": "SUFFICIENT",
          "supported_question_count": 4
        },
        {
          "code": "engineering",
          "label": "Agent 工程实践",
          "short_label": "工程实践",
          "weight": 0.25,
          "score": 84,
          "max_score": 100,
          "level_code": "ABOVE_EXPECTATION",
          "level_label": "超过预期",
          "summary": "能够把超时、重试、幂等和可观测性转化为可执行的工程方案。",
          "evidence_status": "SUFFICIENT",
          "supported_question_count": 4
        },
        {
          "code": "system_design",
          "label": "系统设计与边界意识",
          "short_label": "系统设计",
          "weight": 0.25,
          "score": 80,
          "max_score": 100,
          "level_code": "MEETS_EXPECTATION",
          "level_label": "达到预期",
          "summary": "能够识别可靠性与审计边界，但发布门禁和回退条件仍可更量化。",
          "evidence_status": "SUFFICIENT",
          "supported_question_count": 3
        },
        {
          "code": "problem_solving",
          "label": "分析、取舍与问题解决",
          "short_label": "问题解决",
          "weight": 0.2,
          "score": 82,
          "max_score": 100,
          "level_code": "MEETS_EXPECTATION",
          "level_label": "达到预期",
          "summary": "排查顺序清楚，能够通过分层指标和对照实验缩小问题范围。",
          "evidence_status": "SUFFICIENT",
          "supported_question_count": 4
        },
        {
          "code": "communication",
          "label": "技术表达",
          "short_label": "表达逻辑",
          "weight": 0.1,
          "score": 90,
          "max_score": 100,
          "level_code": "BEST",
          "level_label": "本场最佳",
          "summary": "结论先行、层次清楚，能够主动说明方案之间的取舍。",
          "evidence_status": "SUFFICIENT",
          "supported_question_count": 5
        }
      ],
      "highlights": {
        "strengths": [
          {
            "title": "能把复杂链路拆成可验证的步骤",
            "summary": "在 RAG 召回诊断中，你按数据、切分、索引、检索和重排分层定位，并主动提出使用 Recall@K 建立证据。",
            "evidence_question_ids": [
              "qinst_01J2V84S3F7G6Y2K9P5N1ADQRC"
            ]
          }
        ],
        "primary_gap": {
          "title": "评测标准缺少明确的业务闭环",
          "summary": "你提到了离线指标和人工抽样，但没有充分说明如何把任务成功率、线上反馈与发布门禁连成闭环。",
          "evidence_question_ids": [
            "qinst_01J2VCW5M8Q4R7N1P6K3TACHF"
          ]
        }
      },
      "question_reviews": [
        {
          "question_id": "qinst_01J2V7ZQ6E3N8C1M5K9R4TPAHF",
          "number": 1,
          "topic_code": "agent_memory",
          "topic_label": "基础机制",
          "followup_count": 1,
          "stem": "如何为 Agent 设计短期记忆与长期记忆？",
          "score": 86,
          "max_score": 100,
          "strengths": [
            "准确区分了会话上下文、摘要记忆和可检索长期记忆。",
            "主动提到了敏感信息清理与记忆过期。"
          ],
          "gaps": [
            "没有明确说明长期记忆的写入触发条件。",
            "缺少评估记忆是否真正改善任务成功率的方法。"
          ],
          "improvement": "补充记忆写入门槛、冲突更新规则，以及任务成功率与错误引用率等验证指标。",
          "better_answer_outline": [
            "先按生命周期区分工作记忆、会话摘要与跨会话长期记忆。",
            "再说明写入、检索、更新、过期和隐私隔离规则。",
            "最后用离线回放与线上任务指标验证收益和副作用。"
          ],
          "evidence": [
            {
              "turn_id": "turn_01J2V81G8N5P3Q9M2K7R4TACHF",
              "quote": "长期记忆只写入可复用且经过验证的信息，按用户和任务隔离。"
            }
          ]
        },
        {
          "question_id": "qinst_01J2V84S3F7G6Y2K9P5N1ADQRC",
          "number": 2,
          "topic_code": "rag_retrieval_diagnosis",
          "topic_label": "RAG 诊断",
          "followup_count": 2,
          "stem": "RAG 系统召回效果变差，如何定位问题？",
          "score": 82,
          "max_score": 100,
          "strengths": [
            "排查顺序合理，能通过分阶段指标区分数据、召回、融合与重排问题。",
            "没有把调大 Top-K 当作未经验证的补丁。"
          ],
          "gaps": [
            "没有说明标注集应如何按查询类型分层。",
            "没有充分讨论线上流量变化导致的数据漂移。"
          ],
          "improvement": "固定候选集做旁路对照，并按查询类型分别观察 Recall@K、NDCG 和最终任务命中率。",
          "better_answer_outline": [
            "先确认数据完整性、切分质量、索引和模型版本是否变化。",
            "再分别测量单路召回、融合、重排和生成阶段。",
            "最后通过固定候选集与线上分层流量验证根因。"
          ],
          "evidence": [
            {
              "turn_id": "turn_01J2V8E7Q5M9P2R6K1N4TACHF",
              "quote": "我会固定同一批候选集，分别绕过融合和替换重排模型做对照，再观察 NDCG 与最终命中变化。"
            }
          ]
        },
        {
          "question_id": "qinst_01J2VA2M8Q5R3T7N1P6K4ACHF",
          "number": 3,
          "topic_code": "tool_call_reliability",
          "topic_label": "工程可靠性",
          "followup_count": 2,
          "stem": "如何处理 Agent 工具调用中的超时、重试与幂等？",
          "score": 88,
          "max_score": 100,
          "strengths": [
            "覆盖了超时预算、指数退避、幂等键和人工接管。",
            "能够区分只读工具和具有副作用的工具。"
          ],
          "gaps": [
            "跨工具调用链路的追踪标识说明不足。",
            "补偿操作失败后的最终一致性策略不够完整。"
          ],
          "improvement": "补充端到端 trace_id、工具调用审计记录和补偿失败后的人工处置队列。",
          "better_answer_outline": [
            "先按只读、幂等写入和非幂等写入划分工具风险。",
            "再定义超时预算、重试条件、退避和熔断策略。",
            "最后说明幂等、补偿、审计和人工接管。"
          ],
          "evidence": [
            {
              "turn_id": "turn_01J2VA8N4M9Q2T6R1P5K3ACHF",
              "quote": "对有副作用的工具必须由业务方提供幂等键；如果无法保证幂等，就不能自动重试。"
            }
          ]
        },
        {
          "question_id": "qinst_01J2VB5Q8M4R7T2N9P6K1ACHF",
          "number": 4,
          "topic_code": "workflow_architecture_tradeoff",
          "topic_label": "架构取舍",
          "followup_count": 1,
          "stem": "什么时候选择固定工作流，而不是自主 Agent？",
          "score": 87,
          "max_score": 100,
          "strengths": [
            "从任务确定性、错误成本、审计要求和延迟预算进行选择。",
            "提出优先使用最小自治范围。"
          ],
          "gaps": [
            "缺少逐步放开自治能力的上线策略。",
            "没有给出从自主模式回退到固定流程的量化条件。"
          ],
          "improvement": "增加自治范围的分级灰度方案，并为成功率、成本和高风险错误设置回退阈值。",
          "better_answer_outline": [
            "先根据任务确定性和错误成本选择默认编排方式。",
            "再定义哪些节点允许模型决策、哪些节点必须确定性执行。",
            "最后说明灰度、监控和回退条件。"
          ],
          "evidence": [
            {
              "turn_id": "turn_01J2VBB2Q7M4N9K3T5R1ACHFZ",
              "quote": "我会从最小自治范围开始，只把低风险且需要语义判断的节点交给 Agent。"
            }
          ]
        },
        {
          "question_id": "qinst_01J2VCW5M8Q4R7N1P6K3TACHF",
          "number": 5,
          "topic_code": "agent_evaluation",
          "topic_label": "评测体系",
          "followup_count": 2,
          "stem": "如何评估一个 Agent 系统是否可以上线？",
          "score": 76,
          "max_score": 100,
          "strengths": [
            "提到了任务成功率、工具调用正确率、安全测试和端到端人工评审。"
          ],
          "gaps": [
            "缺少不同风险场景的发布阈值。",
            "没有说明回归集版本管理，以及上线后告警与回滚门槛。"
          ],
          "improvement": "把离线回归、红队、灰度指标、发布阈值和回滚动作组成一套可执行门禁。",
          "better_answer_outline": [
            "先按能力、可靠性、安全和成本建立分层指标。",
            "再为不同风险场景定义回归集与发布阈值。",
            "最后说明灰度监控、告警、回滚和持续数据回流。"
          ],
          "evidence": [
            {
              "turn_id": "turn_01J2VD1R8M5Q3T7N2P6K4ACHF",
              "quote": "我会看任务成功率、工具调用正确率，再做安全测试和端到端人工抽样。"
            }
          ]
        }
      ],
      "suggestions": [
        {
          "priority": 1,
          "priority_code": "HIGHEST",
          "priority_label": "最高优先级",
          "effort_label": "预计 2–3 次专项练习",
          "title": "建立 Agent 评测的完整发布门禁",
          "why": "当前最明显的能力缺口是指标与发布动作没有形成闭环。",
          "actions": [
            "选择一个真实 Agent 任务并建立版本化回归集。",
            "分别定义离线回归、人工红队、灰度监控和回滚阈值。",
            "练习用‘指标—阈值—动作’结构回答评测题。"
          ],
          "completion_criteria": "能在 3 分钟内画出一套从离线到线上的评测闭环。"
        },
        {
          "priority": 2,
          "priority_code": "ENGINEERING_DEPTH",
          "priority_label": "工程深化",
          "effort_label": "结合项目复盘",
          "title": "用量化证据替代‘经验上应该’",
          "why": "排查思路正确，但部分判断缺少基线、对照实验和通过标准。",
          "actions": [
            "为常见排查方案补充指标、基线和对照实验。",
            "重点练习 Recall@K、NDCG、任务成功率和工具调用失败率的适用边界。"
          ],
          "completion_criteria": "每个技术判断都能给出至少一个可执行的验证方式。"
        },
        {
          "priority": 3,
          "priority_code": "COMMUNICATION_UPGRADE",
          "priority_label": "表达升级",
          "effort_label": "保持现有优势",
          "title": "在结论后补充边界与失败条件",
          "why": "当前表达结构清楚，进一步补充边界能提高系统设计答案的可信度。",
          "actions": [
            "继续使用‘结论—拆解—验证’结构。",
            "在结尾主动补充方案失效条件和对应回退路径。"
          ],
          "completion_criteria": "每道系统设计题至少指出一个失败条件和一个回退方案。"
        }
      ],
      "next_interview": {
        "position_code": "ai_agent_development",
        "position_label": "AI Agent 开发",
        "focus_code": "workflow_tool_calling",
        "focus_label": "工作流与工具调用",
        "difficulty": "senior",
        "difficulty_label": "高级",
        "reason": "继续强化评测门禁、工具可靠性和边界设计。"
      },
      "disclaimer": "本报告仅基于本场模拟问答生成，用于个人训练与复盘，不代表真实招聘评价或录用结果。",
      "assessment_metadata": {
        "rubric_version": "agent-interview-rubric-v1",
        "score_scale_version": "score-scale-v1"
      }
    }
  }
}
```

### 7.1 完整与部分报告规则

- `FULL`：正常完成全部主问题；`completion.finish_reason = ALL_QUESTIONS_COMPLETED`。
- `PARTIAL`：用户主动提前结束；只包含已经完成评分的主问题，未完成题不得返回伪造点评。
- 证据不足的 `overall.total_score` 和 `dimension.score` 返回 `null`，相应 `evidence_status = INSUFFICIENT`；是否达到充分证据由服务端产品配置决定，前端不得自行设阈值。
- `PARTIAL` 报告必须提供非空 `completion.limitation_note`，并在页面显著展示。
- `overall.total_score` 由五维分按 `20%/25%/25%/20%/10%` 确定性加权；前端只展示，不重新计算。
- `question_reviews` 按题号升序；一题的主回答与全部追问合并为一个评分单元。

报告尚未生成时：`409 Conflict`

```json
{
  "code": "REPORT_NOT_READY",
  "message": "面试报告尚未生成完成",
  "data": {
    "request_id": "req_01J2VD8Q5M4R7T2N9P6K1ACHF",
    "recoverable": true,
    "details": [
      {
        "interview_status": "REPORTING",
        "suggested_action": "GET_INTERVIEW_SNAPSHOT"
      }
    ]
  }
}
```

主要失败：`INTERVIEW_NOT_FOUND`、`REPORT_NOT_READY`、`REPORT_GENERATION_FAILED`。

## 8. 错误码表

### 8.1 HTTP 状态码使用

| HTTP 状态 | 使用场景 |
|---:|---|
| `200` | 查询成功、SSE 成功建立、幂等重放既有结果 |
| `201` | 面试会话首次创建成功 |
| `400` | JSON 格式错误、缺少必要头、未确认规则或部分报告 |
| `404` | 会话资源不存在 |
| `409` | 当前会话状态冲突、版本过期、幂等冲突、报告未就绪 |
| `422` | 字段格式、枚举、长度或语义校验失败 |
| `429` | API 自身的请求频率限制；不直接暴露上游供应商响应体 |
| `500` | 未分类的服务端错误 |
| `503` | 服务未就绪、数据库繁忙、上游模型暂不可用 |
| `504` | 上游模型调用超时 |

### 8.2 业务错误码

| `code` | HTTP | 可恢复 | 触发条件 | 前端处理 |
|---|---:|:---:|---|---|
| `INVALID_JSON` | 400 | 是 | 请求体不是合法 JSON | 保留输入并提示重试 |
| `VALIDATION_ERROR` | 422 | 是 | 通用字段校验失败 | 按 `details.field` 标记表单项 |
| `IDEMPOTENCY_KEY_REQUIRED` | 400 | 是 | 需要幂等键的 POST 未提供请求头 | 生成键后重新请求 |
| `IDEMPOTENCY_CONFLICT` | 409 | 否 | 同一幂等键对应不同请求体 | 生成新键，并先读取快照 |
| `RULES_NOT_CONFIRMED` | 400 | 是 | 创建会话时未确认当前规则 | 返回开始页完成确认 |
| `RULES_VERSION_EXPIRED` | 409 | 是 | 前端提交的规则版本已过期 | 重新读取配置并提示确认 |
| `UNSUPPORTED_OPTION` | 422 | 是 | 岗位、侧重点或难度不在目录中 | 刷新配置选项 |
| `INTERVIEW_NOT_FOUND` | 404 | 否 | 会话 ID 不存在 | 返回开始页，不显示空报告 |
| `INTERVIEW_ALREADY_STARTED` | 409 | 是 | 已启动会话使用新键再次调用开始 | 读取会话快照 |
| `INVALID_INTERVIEW_STATE` | 409 | 是 | 当前状态不允许该命令 | 读取快照并按 `available_actions` 重建按钮 |
| `STALE_SESSION_VERSION` | 409 | 是 | `expected_row_version` 与服务端不一致 | 读取快照，禁止盲目重发 |
| `STALE_INTERRUPT` | 409 | 是 | 回答对应的 interrupt 或消息已不是当前问题 | 读取快照并要求用户确认当前回答 |
| `ACTIVE_OPERATION_EXISTS` | 409 | 是 | 同一会话已有运行中的图执行 | 禁用重复操作并轮询一次快照 |
| `ANSWER_EMPTY` | 422 | 是 | 回答去除空白后为空 | 保持输入框焦点；不计追问 |
| `ANSWER_TOO_LONG` | 422 | 是 | 回答超过 `pending_answer.max_length` | 显示长度限制；不计追问 |
| `PARTIAL_REPORT_NOT_CONFIRMED` | 400 | 是 | 提前结束未明确确认部分报告 | 保持确认弹窗 |
| `RETRY_NOT_AVAILABLE` | 409 | 是 | 当前不存在可恢复失败步骤 | 读取会话快照 |
| `REPORT_NOT_READY` | 409 | 是 | 会话尚未完成报告持久化 | 显示生成中并读取快照 |
| `QUESTION_GENERATION_FAILED` | 503 | 是 | 主问题或追问生成失败且自动重试耗尽 | 显示“重试当前步骤” |
| `ASSESSMENT_FAILED` | 503 | 是 | 回答评估/结构校验失败且自动修复耗尽 | 显示“重试当前步骤”；不得假设已完成本题 |
| `REPORT_GENERATION_FAILED` | 503 | 是 | 报告生成或持久化失败 | 保留逐题结果，只重试报告节点 |
| `LLM_RATE_LIMITED` | 503 | 是 | DeepSeek 上游限流 | 按服务端建议稍后重试 |
| `LLM_TIMEOUT` | 504 | 是 | DeepSeek 调用超时 | 重试当前步骤，不重复提交回答 |
| `DATABASE_BUSY` | 503 | 是 | SQLite 写锁等待超过限制 | 短暂等待后使用原幂等键重试 |
| `SERVICE_NOT_READY` | 503 | 是 | 必要配置、题库或数据库未就绪 | 禁用开始按钮，稍后检查就绪状态 |
| `RATE_LIMITED` | 429 | 是 | API 自身限流 | 使用 `Retry-After` 后重试 |
| `INTERNAL_ERROR` | 500 | 视情况 | 未分类服务端异常 | 记录 `request_id`，读取快照后给出兜底入口 |

### 8.3 标准错误响应示例

状态冲突：

```json
{
  "code": "STALE_INTERRUPT",
  "message": "当前问题已经变化，请刷新面试状态后重新确认回答",
  "data": {
    "request_id": "req_01J2VE2M8Q5R3T7N1P6K4ACHF",
    "recoverable": true,
    "details": [
      {
        "submitted_interrupt_id": "intr_01J2V801D4M9Q6R7N2K5T3ACPH",
        "current_interrupt_id": "intr_01J2V8C0T1FVH8M6Z3K9Q5R2AP",
        "suggested_action": "GET_INTERVIEW_SNAPSHOT"
      }
    ]
  }
}
```

上游超时发生在建立 SSE 之前：

```json
{
  "code": "LLM_TIMEOUT",
  "message": "面试官响应超时，可重试当前步骤",
  "data": {
    "request_id": "req_01J2VE3Q4M9R7T2N5P6K1ACHF",
    "recoverable": true,
    "details": [
      {
        "failed_step": "compose_question",
        "retry_after_seconds": 2,
        "suggested_action": "RETRY_FAILED_STEP"
      }
    ]
  }
}
```

错误响应不得包含 DeepSeek API Key、完整系统提示、checkpoint 内容、Python traceback 或数据库路径。

## 9. 前端消费规则

### 9.1 页面初始化

- 开始页并行读取 `/interview-options` 和 `/health/ready`；未就绪时保留配置展示，但禁用“开始模拟面试”。
- 历史页读取 `GET /interviews`；分页切换只替换列表数据，并保留加载、空数据和错误状态。
- 面试页只能凭 `interview_id` 读取快照初始化，不依赖上一页面内存中的问题或进度。
- 报告页只能凭 `interview_id` 读取报告；收到 `REPORT_NOT_READY` 时读取会话快照决定等待、重试或返回面试页。

### 9.2 状态归属

| 数据 | 唯一事实来源 | 前端允许的处理 |
|---|---|---|
| 会话状态、题号、完成数、追问数 | 会话快照与 `progress.updated` | 整体替换，不自行递增 |
| 正式消息 | 快照 `messages` 与 `question.completed` | 按消息 ID 去重 |
| 临时流式文本 | `question.delta` | 只做临时缓冲；断流即丢弃 |
| 回答是否已保存 | `answer.accepted` 或快照正式消息 | 未确认前保留本地待发送状态 |
| 报告是否可读 | `report.completed` 或最终会话快照 | 可读后再请求报告 |
| 分数、评价和建议 | 报告接口 | 只展示，不推导、不重算 |
| 已用时长 | 快照 `started_at`、`server_time`、`elapsed_seconds` | 用服务端时间校准后本地每秒更新 |

### 9.3 提交按钮规则

只有同时满足以下条件时允许提交：

- 会话状态为 `WAITING_ANSWER`。
- `pending_answer` 非空。
- 去除首尾空白后的长度在 `min_length` 与 `max_length` 之间。
- 当前没有活动 SSE 命令。

`Ctrl + Enter` 与点击提交按钮必须调用同一提交函数，并复用同一个 `Idempotency-Key`，不能形成两个并行请求。

### 9.4 SSE 消费伪时序

```text
发起 POST SSE
  -> stream.open：锁定当前操作
  -> answer.accepted：确认本地回答已保存（开始接口无此事件）
  -> question.changed：需要时切换主问题
  -> question.meta + question.delta*：渲染临时问题
  -> question.completed：替换为权威问题消息
  -> progress.updated：替换进度
  -> waiting.answer：解锁输入框
  -> stream.done：关闭本次流
```

最后一题或提前结束时，后半段替换为：

```text
report.delta* -> report.completed -> interview.completed -> stream.done
```

## 10. 前端页面—接口映射表

### 10.1 开始面试页 `index.html`

| 页面数据或交互 | 接口/来源 | 字段或动作 | 说明 |
|---|---|---|---|
| 系统已就绪状态 | `GET /health/ready` | `data.status`、`message` | 非 `READY` 时禁用开始按钮 |
| `MVP / 01` | `GET /interview-options` | `product.release_label` | 版本展示 |
| 岗位方向 | `GET /interview-options` | `positions[]` | MVP 只有 AI Agent 开发，仍按数组建模 |
| 能力侧重点 | `GET /interview-options` | `positions[].focus_options[]` | 应用工程、RAG 知识应用、工具与工作流 |
| 初级/中级/高级 | `GET /interview-options` | `difficulties[]` | 显示名称和难度说明 |
| 默认选择 | `GET /interview-options` | `defaults` | 前端不写死默认项 |
| 5 道主问题 | `GET /interview-options` | `interview_spec.main_question_count` | 面试规格 |
| 每题最多追问 2 次 | `GET /interview-options` | `interview_spec.max_followups_per_question` | 面试规格 |
| 预计用时 25 分钟 | `GET /interview-options` | `interview_spec.estimated_duration_minutes` | 面试规格 |
| 问题预览 | `GET /interview-options` | `preview_question` | 仅首页示例，不加入当前会话去重集合 |
| 面试中不显示分数 | `GET /interview-options` | `rules.items`、`interview_spec.feedback_timing` | 规则说明 |
| 练习用途说明 | `GET /interview-options` | `usage_disclaimer` | 开始前必须可见 |
| 点击开始 | `POST /interviews` | 提交岗位、侧重点、难度、规则确认 | 成功后得到 `interview_id` |
| 进入第一题 | `POST /interviews/{id}/start/stream` | 开始命令与第一题事件 | 只在会话创建成功后调用 |
| 品牌、营销标题、页脚 | 前端静态文案 | 无接口 | 不属于业务数据 |
| 浅色/深色切换 | 前端本地状态 | 无接口 | 使用本地存储保存偏好 |

### 10.2 面试进行页 `interview.html`

| 页面数据或交互 | 接口/来源 | 字段或事件 | 说明 |
|---|---|---|---|
| 岗位与难度标题 | `GET /interviews/{id}` | `interview.config` | 例如“AI Agent 开发 · 中级” |
| 进行中/等待回答/生成报告 | 快照 + SSE | `status`、`stream.open`、`stream.done` | 不根据动画自行推断状态 |
| 当前第几题/共几题 | 快照 + SSE | `progress.current_question_number`、`total_question_count` | 与完成题数分开显示 |
| 已完成题数与百分比 | 快照 + SSE | `completed_question_count`、`completion_percent` | 仅完成评分后增加 |
| 当前主题 | 快照 + SSE | `current_question.display_title`、`progress.current_topic_label` | 例如 RAG 召回诊断 |
| 面试官与我的消息 | `GET /interviews/{id}` | `messages[]` | 刷新后完整恢复 |
| 问题 token 流 | POST SSE | `question.meta`、`question.delta`、`question.completed` | `completed` 为最终文本 |
| 主问题/追问标识 | 快照 + SSE | `message.kind`、`followup_level` | 生成“追问 1/2”等标签 |
| 已用时长 | `GET /interviews/{id}` | `timing` | 服务端校准，前端本地计时 |
| 当前追问 1/2 | 快照 + SSE | `progress.current_followup_count`、`max_followups_per_question` | 不允许显示第 3 次追问 |
| 追问层级节点 | 快照 + SSE | 同上 | 0/1/2 决定节点状态 |
| 五题问题地图 | `GET /interviews/{id}` | `question_map[]` | 显示完成、进行中和等待状态 |
| 输入框 placeholder | 快照 + SSE | `pending_answer.placeholder` | 主问题与追问可不同 |
| 最大 1200 字 | 快照 + SSE | `pending_answer.max_length` | 实时字数由前端本地计算 |
| 提交回答 | `POST /interviews/{id}/answers/stream` | `interrupt_id`、`answer_to_turn_id`、`content` | 同时获得追问、下一题或结束事件 |
| 不立即展示评分 | 快照/固定规则 | `score_visibility` | 前端不得访问隐藏评分数据 |
| 提前结束弹窗的完成数 | `GET /interviews/{id}` | `completed_question_count`、`total_question_count` | 文案必须基于实际完成题数 |
| 确认提前结束 | `POST /interviews/{id}/finish/stream` | `confirm_partial_report = true` | 生成 `PARTIAL` 报告 |
| 错误后的重试 | `POST /interviews/{id}/retry/stream` | `failed_operation_id` | 仅 `available_actions.retry = true` 时展示 |
| SSE 断流恢复 | `GET /interviews/{id}` | 完整会话快照 | 不使用页面已显示 token 推进状态 |
| 主题切换、Ctrl+Enter、字数计数 | 前端本地交互 | 无接口 | 不改变服务端业务状态 |

### 10.3 面试报告页 `report.html`

| 页面数据或交互 | 接口/来源 | 字段 | 说明 |
|---|---|---|---|
| 报告日期 | `GET /interviews/{id}/report` | `report.generated_at` | 前端按本地时区格式化 |
| 总体标题与摘要 | 同上 | `overall.headline`、`overall.summary` | 服务端基于证据生成 |
| 岗位、侧重点、难度 | 同上 | `config` | 页面标签数据 |
| 完成题数 | 同上 | `completion.completed_question_count`、`total_question_count` | 部分报告必须如实显示 |
| 总用时 | 同上 | `completion.duration_seconds` | 前端格式化为 `31:26` |
| 总分 | 同上 | `overall.total_score`、`max_score` | 证据不足时显示“暂不评分” |
| 表现良好/超过预期 | 同上 | `overall.level_label`、`expectation_label` | 不由前端根据分数猜测 |
| 分数区间图例 | 同上 | `score_scale[]` | 与评分版本一致 |
| 五个能力维度 | 同上 | `dimensions[]` | 正式实现必须是五维，不沿用原型四维 |
| 维度分、标签和说明 | 同上 | `dimensions[].score`、`level_label`、`summary` | `null` 时展示证据不足 |
| 明确优势 | 同上 | `highlights.strengths[]` | 可回溯题目 ID |
| 主要短板 | 同上 | `highlights.primary_gap` | 不把“未体现”写成“一定不会” |
| 五道逐题得分 | 同上 | `question_reviews[]` | 部分报告只返回已完成题 |
| 题目、追问次数、得分 | 同上 | `stem`、`followup_count`、`score` | 折叠列表摘要 |
| 回答亮点 | 同上 | `question_reviews[].strengths` | 展开详情 |
| 可以更好 | 同上 | `gaps`、`improvement`、`better_answer_outline` | 展开详情 |
| 证据摘录 | 同上 | `question_reviews[].evidence[]` | 只能来自本场用户回答 |
| 三条改进建议 | 同上 | `suggestions[]` | 按 `priority` 升序且必须恰好三条 |
| 建议标签与投入 | 同上 | `priority_label`、`effort_label` | 例如“最高优先级” |
| 行动与完成标志 | 同上 | `actions[]`、`completion_criteria` | 必须可执行、可验证 |
| 下一场推荐 | 同上 | `next_interview` | 用于预填下一场配置 |
| 完整性限制 | 同上 | `completeness`、`limitation_note` | `PARTIAL` 时显著展示 |
| 练习用途声明 | 同上 | `disclaimer` | 报告末尾必须显示 |
| 重新面试/开始新面试 | 前端路由 + 可选预填 | `next_interview` | 返回开始页；仍需创建新会话 |
| 主题切换 | 前端本地状态 | 无接口 | 与报告数据无关 |

### 10.4 历史面试页 `/history`

| 页面数据或交互 | 接口/来源 | 字段 | 说明 |
|---|---|---|---|
| 历史总数、完整数、提前结束数 | `GET /interviews` | `summary` | 服务端统计全部历史，不只统计当前页 |
| 历史记录列表 | 同上 | `items[]` | 按完成时间倒序 |
| 面试日期 | 同上 | `completed_at`、`generated_at` | 前端按本地时区格式化 |
| 岗位、侧重点、难度 | 同上 | `items[].config` | 不从题目或标题推断 |
| 完整/提前结束标签 | 同上 | `status_label`、`completeness` | `PARTIAL` 显著标识 |
| 完成题数与用时 | 同上 | `completion` | 只展示服务端记录值 |
| 总分和等级 | 同上 | `overall` | `total_score = null` 时展示“暂不评分” |
| 报告摘要标题 | 同上 | `overall.headline` | 历史卡片摘要 |
| 查看报告 | 前端路由 | `interview_id` | 跳转 `/interviews/{id}/report` 并重新读取完整报告 |
| 上一页/下一页 | `GET /interviews` | `pagination` | 页码写入 URL 查询参数 |
| 加载、空数据、错误状态 | 前端状态 | 无接口 | 错误时提供重新加载入口 |
| 浅色/深色切换 | 前端本地状态 | 无接口 | 与其他页面共享主题偏好 |

## 11. 契约验收清单

前后端联调前必须同时满足：

- 所有普通响应均符合 `code/message/data`，错误响应含 `request_id`。
- OpenAPI 中的字段、枚举、必填性、可空性和本文档一致。
- 创建、开始、回答、结束和重试均通过幂等测试。
- 并发提交同一回答只生成一条候选人消息，题号和追问数只推进一次。
- 第 2 次追问后绝不出现第 3 次追问。
- SSE 每个操作从 `sequence = 1` 单调递增，正常路径以 `stream.done` 结束。
- 断流后通过快照能够恢复正式消息、当前问题、追问层级和输入约束。
- 面试进行页的任何接口和事件均不泄露分数或评分证据。
- 完整报告包含五维分、五道逐题点评和三条改进建议。
- 部分报告不包含未完成题的虚假点评；证据不足时分数为 `null`。
- 历史列表只包含已生成报告的完整/部分面试，排序、总数和分页在多页情况下保持稳定。
- 报告总分由后端按正式五维权重计算，前端不重复计算。
- 原型页面的所有动态数据点均已在第 10 节找到接口来源或明确标记为前端本地数据。

## 12. 契约变更规则

1. 新增可选字段：契约补丁版本递增，例如 `1.0.0` → `1.0.1`。
2. 新增枚举值、改变事件顺序或字段语义：至少递增次版本，并验证旧前端的未知值处理。
3. 删除字段、改变类型、改变可空性或重命名事件：属于破坏性变更，必须升级 API 主版本和 SSE `schema_version`。
4. 任何变更先修改本文档与 schema，再修改后端和前端；不得以“前端暂时兼容”代替契约评审。
5. 前端四维原型正式迁移时，以本文档五维字段为准；不提供长期的四维兼容层。
