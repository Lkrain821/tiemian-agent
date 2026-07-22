"""FastAPI dependency accessors."""

from fastapi import Request

from app.application.container import ApplicationContainer


def get_container(request: Request) -> ApplicationContainer:
    return request.app.state.container


def get_request_id(request: Request) -> str:
    return request.state.request_id

