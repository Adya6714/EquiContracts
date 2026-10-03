"""EquiContracts Phase 0 walking-skeleton API."""

import secrets
from collections.abc import Awaitable, Callable
from typing import cast

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from starlette.requests import Request
from starlette.responses import Response

from .routers import client_dashboard, inbound, projects, review

app = FastAPI(title="EquiContracts API", version="0.1.0")
app.include_router(projects.router)
app.include_router(inbound.router)
app.include_router(review.router)
app.include_router(client_dashboard.router)


@app.exception_handler(HTTPException)
async def http_error_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    del request
    detail = cast(object, exc.detail)
    if isinstance(detail, dict):
        content = cast(dict[str, object], detail)
    else:
        content = {"detail": str(detail), "code": "http_error"}
    return JSONResponse(status_code=exc.status_code, content=content)


@app.middleware("http")
async def request_id_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = request.headers.get("x-request-id") or secrets.token_hex(12)
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
