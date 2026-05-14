import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any

import qrcode
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from qrcode.image.svg import SvgPathImage

from src.application.runtime import SimulatorRuntime
from src.domain.models import DataType, GeneratorSettings, SimulatorSettings, SimulatorVariable
from src.infrastructure.logger import get_logger
from src.infrastructure.opcua_server import AsyncuaSimulatorServer


DEFAULT_PUBLIC_WEB_URL = "http://localhost:8080"
LOGGER = get_logger(__name__)


class VariableValueRequest(BaseModel):
    value: Any


class AutoUpdateRequest(BaseModel):
    enabled: bool


class GeneratorRequest(BaseModel):
    kind: str = "sine"
    amplitude: float
    period_ticks: int


class CreateVariableRequest(BaseModel):
    name: str
    data_type: DataType
    default: Any
    node_id: str | None = None
    unit: str | None = None
    writable: bool = True
    generator: GeneratorRequest | None = None


class VariableResponse(BaseModel):
    name: str
    node_id: str
    data_type: str
    value: Any
    unit: str | None
    writable: bool
    auto_update: bool
    has_generator: bool


class VariablesResponse(BaseModel):
    variables: list[VariableResponse]


class HealthResponse(BaseModel):
    status: str
    opcua_endpoint: str


class AccessResponse(BaseModel):
    public_url: str


def create_app(
    settings: SimulatorSettings,
    *,
    runtime: SimulatorRuntime | None = None,
    static_dir: Path | None = None,
    public_web_url: str | None = None,
) -> FastAPI:
    app_runtime = runtime or SimulatorRuntime(settings, AsyncuaSimulatorServer())
    resolved_public_url = public_web_url or os.getenv("PUBLIC_WEB_URL", DEFAULT_PUBLIC_WEB_URL)
    resolved_static_dir = static_dir or Path("frontend/dist")

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        _log_startup_qr(resolved_public_url)
        await app_runtime.start()
        try:
            yield
        finally:
            await app_runtime.stop()

    app = FastAPI(title="OPC UA Simulator", lifespan=lifespan)

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            status="ok" if app_runtime.started else "starting",
            opcua_endpoint=settings.server.endpoint,
        )

    @app.get("/api/access", response_model=AccessResponse)
    async def access() -> AccessResponse:
        return AccessResponse(public_url=resolved_public_url)

    @app.get("/api/qr.svg")
    async def qr_svg() -> Response:
        image = qrcode.make(resolved_public_url, image_factory=SvgPathImage)
        output = BytesIO()
        image.save(output)
        return Response(content=output.getvalue(), media_type="image/svg+xml")

    @app.get("/api/variables", response_model=VariablesResponse)
    async def list_variables() -> VariablesResponse:
        return VariablesResponse(
            variables=[_variable_response(variable) for variable in app_runtime.list_variables()]
        )

    @app.patch("/api/variables/{name}", response_model=VariableResponse)
    async def set_variable(name: str, request: VariableValueRequest) -> VariableResponse:
        try:
            variable = await app_runtime.set_value(name, request.value)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=f"unknown variable: {name}") from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _variable_response(variable)

    @app.post("/api/variables", response_model=VariableResponse, status_code=201)
    async def create_variable(request: CreateVariableRequest) -> VariableResponse:
        try:
            variable = await app_runtime.add_variable(
                name=request.name,
                node_id=request.node_id,
                data_type=request.data_type,
                default=request.default,
                unit=request.unit,
                writable=request.writable,
                generator=(
                    GeneratorSettings(
                        kind=request.generator.kind,
                        amplitude=request.generator.amplitude,
                        period_ticks=request.generator.period_ticks,
                    )
                    if request.generator is not None
                    else None
                ),
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _variable_response(variable)

    @app.post("/api/variables/{name}/auto", response_model=VariableResponse)
    async def set_auto_update(name: str, request: AutoUpdateRequest) -> VariableResponse:
        try:
            variable = await app_runtime.set_auto_update(name, request.enabled)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=f"unknown variable: {name}") from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _variable_response(variable)

    @app.get("/api/events")
    async def events() -> StreamingResponse:
        return StreamingResponse(
            _event_stream(app_runtime),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    if resolved_static_dir.exists():
        assets_dir = resolved_static_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(resolved_static_dir / "index.html")

    return app


def _variable_response(variable: SimulatorVariable) -> VariableResponse:
    return VariableResponse(
        name=variable.name,
        node_id=variable.node_id,
        data_type=variable.data_type.value,
        value=variable.value,
        unit=variable.unit,
        writable=variable.definition.writable,
        auto_update=variable.auto_update,
        has_generator=variable.definition.generator is not None,
    )


async def _event_stream(runtime: SimulatorRuntime) -> AsyncIterator[str]:
    while True:
        payload = VariablesResponse(
            variables=[_variable_response(variable) for variable in runtime.list_variables()]
        )
        yield f"event: variables\ndata: {payload.model_dump_json()}\n\n"
        await asyncio.sleep(1)


def _log_startup_qr(public_web_url: str) -> None:
    output = StringIO()
    qr = qrcode.QRCode(border=1)
    qr.add_data(public_web_url)
    qr.make(fit=True)
    qr.print_ascii(out=output, invert=True)
    LOGGER.info("web UI available url=%s", public_web_url)
    LOGGER.info("scan to open web UI on your phone:\n%s", output.getvalue().rstrip())
