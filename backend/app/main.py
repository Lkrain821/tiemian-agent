"""FastAPI application factory and managed dependency lifecycle."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.routes import router
from app.application.commands import InterviewCommands
from app.application.container import ApplicationContainer
from app.application.locks import SessionOperationLocks
from app.application.queries import InterviewQueries
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.logging import configure_logging
from app.core.settings import Settings, get_settings
from app.graph.checkpoint import sqlite_checkpointer
from app.graph.dependencies import GraphDependencies
from app.graph.registry import GraphRegistry
from app.graph.v1.builder import build_interview_graph
from app.llm.client import DeepSeekClient
from app.repositories.database import Database
from app.repositories.unit import Repositories
from app.services.question_bank import QuestionBank


logger = logging.getLogger(__name__)


def create_app(*, settings: Settings | None = None, llm: Any | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(resolved_settings.log_level)
        database = Database(
            resolved_settings.app_db_path,
            resolved_settings.sqlite_busy_timeout_ms,
        )
        await database.connect()
        await database.initialize()
        repositories = Repositories(database)
        question_bank = QuestionBank.load(resolved_settings.question_bank_path)
        owned_llm = llm is None
        llm_client = llm or DeepSeekClient(resolved_settings)
        async with sqlite_checkpointer(resolved_settings.checkpoint_db_path) as checkpointer:
            graph_registry = GraphRegistry()
            graph_registry.register(
                "interview_v1",
                build_interview_graph(
                    GraphDependencies(
                        settings=resolved_settings,
                        repositories=repositories,
                        question_bank=question_bank,
                        llm=llm_client,
                    ),
                    checkpointer,
                ),
            )
            queries = InterviewQueries(
                repositories, question_bank, resolved_settings.answer_max_length
            )
            commands = InterviewCommands(
                repositories,
                queries,
                graph_registry,
                SessionOperationLocks(),
                answer_max_length=resolved_settings.answer_max_length,
            )
            app.state.container = ApplicationContainer(
                settings=resolved_settings,
                database=database,
                repositories=repositories,
                question_bank=question_bank,
                llm=llm_client,
                graph_registry=graph_registry,
                queries=queries,
                commands=commands,
            )
            try:
                yield
            finally:
                if owned_llm and hasattr(llm_client, "close"):
                    await llm_client.close()
                await database.close()

    app = FastAPI(
        title="铁面 API",
        version=resolved_settings.api_version,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Accept", "Idempotency-Key"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or new_id("req")
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        if not response.headers.get("content-type", "").startswith("text/event-stream"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "data": {
                    "request_id": request.state.request_id,
                    "recoverable": exc.recoverable,
                    "details": exc.details,
                },
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        invalid_json = any(item.get("type") == "json_invalid" for item in errors)
        unsupported = any(
            len(item.get("loc", ())) > 1
            and item["loc"][-1] in {"position_code", "focus_code", "difficulty"}
            for item in errors
        )
        code = "INVALID_JSON" if invalid_json else "UNSUPPORTED_OPTION" if unsupported else "VALIDATION_ERROR"
        status_code = 400 if invalid_json else 422
        message = {
            "INVALID_JSON": "请求体不是合法 JSON",
            "UNSUPPORTED_OPTION": "岗位、侧重点或难度选项不受支持",
            "VALIDATION_ERROR": "请求字段校验失败",
        }[code]
        details = [
            {
                "field": ".".join(str(part) for part in item.get("loc", ())[1:]),
                "reason": item.get("type", "validation_error"),
            }
            for item in errors
        ]
        return JSONResponse(
            status_code=status_code,
            content={
                "code": code,
                "message": message,
                "data": {
                    "request_id": request.state.request_id,
                    "recoverable": True,
                    "details": details,
                },
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled request error", extra={"request_id": request.state.request_id})
        return JSONResponse(
            status_code=500,
            content={
                "code": "INTERNAL_ERROR",
                "message": "服务暂时无法处理请求",
                "data": {
                    "request_id": request.state.request_id,
                    "recoverable": True,
                    "details": [],
                },
            },
        )

    app.include_router(router)
    return app


app = create_app()
