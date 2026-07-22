# 铁面后端

FastAPI + LangGraph 的面试状态机实现。业务数据与 LangGraph checkpoint 分别持久化到 SQLite；所有 DeepSeek 调用只经过 `app/llm/client.py`。

## 本地启动

1. 在仓库根目录配置 `.env`。变量示例见 `backend/.env.example`，API Key 不要提交到版本库。
2. 在 `backend/` 目录安装依赖：

   ```powershell
   uv sync --python 3.12
   ```

3. 启动 API：

   ```powershell
   uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

4. 查看接口：`http://127.0.0.1:8000/docs`；就绪检查：`http://127.0.0.1:8000/api/v1/health/ready`。

## 测试

```powershell
uv run pytest -q
```

测试统一使用确定性的 LLM 替身，不读取真实 API Key，也不会产生模型费用。真实 DeepSeek 联调应显式标记为 `live`，不纳入默认测试。
