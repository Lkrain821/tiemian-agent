# 铁面 · AI 面试官

面向 AI Agent 开发岗位的模拟技术面试项目。系统会根据回答动态追问、逐题评分，并在面试结束后生成可回溯的评估报告。

## 技术栈

- 后端：Python 3.12、FastAPI、LangChain、LangGraph、SQLite
- 模型：DeepSeek OpenAI 兼容接口
- 前端：Vue 3、Vite

## 项目结构

- `backend/`：FastAPI API、LangGraph 状态机与测试
- `frontend/`：Vue 3 正式前端
- `data/`：题库种子文件；运行时数据库不会提交到 Git
- `docs/`：需求、架构和 API 契约
- `prototype/`：早期静态 UI 原型

## 本地运行

先参考 `backend/.env.example` 在仓库根目录创建 `.env`，不要提交真实 API Key。

```powershell
cd backend
uv sync --python 3.12
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

另开终端启动前端：

```powershell
cd frontend
bun install
bun run dev
```

访问 `http://127.0.0.1:5173/`。

## 验证

```powershell
cd backend
uv run pytest -q

cd ..\frontend
bun run build
```

详细设计见 `docs/01-需求文档.md`、`docs/02-架构设计.md` 和 `docs/03-API接口文档.md`。
