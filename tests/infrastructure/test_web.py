from pathlib import Path

from fastapi.testclient import TestClient

from src.application.runtime import SimulatorRuntime
from src.domain.models import (
    DataType,
    GeneratorSettings,
    RuntimeSettings,
    ServerSettings,
    SimulatorSettings,
    VariableDefinition,
)
from src.infrastructure.web import create_app


class FakeServer:
    async def start(self, settings, state) -> None:
        return None

    async def sync(self, state) -> None:
        return None

    async def add_variable(self, variable) -> None:
        return None

    async def stop(self) -> None:
        return None


async def long_sleep(_: float) -> None:
    import asyncio

    await asyncio.sleep(60)


def test_api_lists_variables_and_access_url() -> None:
    client = _client()

    with client:
        variables_response = client.get("/api/variables")
        access_response = client.get("/api/access")

    assert variables_response.status_code == 200
    assert variables_response.json()["variables"][0]["name"] == "pump_running"
    assert access_response.json() == {"public_url": "http://phone.local:8000"}


def test_api_updates_typed_values() -> None:
    client = _client()

    with client:
        response = client.patch("/api/variables/pump_running", json={"value": 1})

    assert response.status_code == 200
    assert response.json()["value"] is True


def test_api_rejects_invalid_typed_values() -> None:
    client = _client()

    with client:
        response = client.patch("/api/variables/pump_running", json={"value": 2})

    assert response.status_code == 400
    assert "boolean" in response.json()["detail"]


def test_api_rejects_read_only_values() -> None:
    client = _client()

    with client:
        response = client.patch("/api/variables/status", json={"value": "running"})

    assert response.status_code == 403


def test_api_sets_auto_mode_for_generated_variables() -> None:
    client = _client()

    with client:
        response = client.post("/api/variables/wave/auto", json={"enabled": False})

    assert response.status_code == 200
    assert response.json()["auto_update"] is False


def test_api_creates_runtime_variable_with_default_node_id() -> None:
    client = _client()

    with client:
        response = client.post(
            "/api/variables",
            json={
                "name": "runtime_sensor",
                "data_type": "int",
                "default": "3",
            },
        )
        update_response = client.patch(
            "/api/variables/runtime_sensor",
            json={"value": "4"},
        )

    assert response.status_code == 201
    assert response.json()["node_id"] == "ns=2;s=runtime_sensor"
    assert response.json()["value"] == 3
    assert update_response.status_code == 200
    assert update_response.json()["value"] == 4


def test_api_rejects_duplicate_runtime_variable() -> None:
    client = _client()

    with client:
        first = client.post(
            "/api/variables",
            json={"name": "runtime_sensor", "data_type": "float", "default": 1.0},
        )
        second = client.post(
            "/api/variables",
            json={"name": "runtime_sensor", "data_type": "float", "default": 1.0},
        )

    assert first.status_code == 201
    assert second.status_code == 400
    assert "duplicate variable name" in second.json()["detail"]


def test_api_creates_generated_runtime_variable_and_sets_auto_mode() -> None:
    client = _client()

    with client:
        create_response = client.post(
            "/api/variables",
            json={
                "name": "runtime_wave",
                "data_type": "float",
                "default": 1.0,
                "generator": {
                    "kind": "sine",
                    "amplitude": 2.0,
                    "period_ticks": 10,
                },
            },
        )
        auto_response = client.post(
            "/api/variables/runtime_wave/auto",
            json={"enabled": False},
        )

    assert create_response.status_code == 201
    assert create_response.json()["has_generator"] is True
    assert create_response.json()["auto_update"] is True
    assert auto_response.status_code == 200
    assert auto_response.json()["auto_update"] is False


def test_api_creates_totalizer_runtime_variable_with_boolean_link() -> None:
    client = _client()

    with client:
        create_response = client.post(
            "/api/variables",
            json={
                "name": "runtime_total",
                "data_type": "float",
                "default": 0.0,
                "unit": "liters",
                "generator": {
                    "kind": "totalizer",
                    "rate_liters_per_minute": 60.0,
                    "enabled_by": "pump_running",
                },
            },
        )

    assert create_response.status_code == 201
    payload = create_response.json()
    assert payload["has_generator"] is True
    assert payload["generator"]["kind"] == "totalizer"
    assert payload["generator"]["rate_liters_per_minute"] == 60.0
    assert payload["generator"]["enabled_by"] == "pump_running"


def test_api_rejects_totalizer_runtime_variable_with_missing_link() -> None:
    client = _client()

    with client:
        response = client.post(
            "/api/variables",
            json={
                "name": "runtime_total",
                "data_type": "float",
                "default": 0.0,
                "generator": {
                    "kind": "totalizer",
                    "rate_liters_per_minute": 60.0,
                    "enabled_by": "missing_valve",
                },
            },
        )

    assert response.status_code == 400
    assert "enabled_by" in response.json()["detail"]


def test_api_rejects_generator_for_boolean_runtime_variable() -> None:
    client = _client()

    with client:
        response = client.post(
            "/api/variables",
            json={
                "name": "bad_generator",
                "data_type": "boolean",
                "default": False,
                "generator": {
                    "kind": "sine",
                    "amplitude": 1.0,
                    "period_ticks": 10,
                },
            },
        )

    assert response.status_code == 400
    assert "generators" in response.json()["detail"]


def test_api_qr_svg_returns_image() -> None:
    client = _client()

    with client:
        response = client.get("/api/qr.svg")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/svg+xml"
    assert b"<svg" in response.content


def test_api_browser_defaults_normalizes_local_endpoint() -> None:
    settings = _settings()
    settings = SimulatorSettings(
        server=ServerSettings(endpoint="opc.tcp://0.0.0.0:4840"),
        runtime=settings.runtime,
        variables=settings.variables,
    )
    runtime = SimulatorRuntime(settings, FakeServer(), sleep=long_sleep)
    client = TestClient(create_app(settings, runtime=runtime))

    with client:
        response = client.get("/api/browser/defaults")

    assert response.status_code == 200
    assert response.json() == {
        "endpoint": "opc.tcp://127.0.0.1:4840",
        "max_depth": 6,
        "max_nodes": 500,
    }


def test_api_browser_rejects_empty_endpoint() -> None:
    client = _client()

    with client:
        response = client.post("/api/browser/browse", json={"endpoint": " "})

    assert response.status_code == 400
    assert "endpoint" in response.json()["detail"]


def test_api_browser_rejects_invalid_expand_limits() -> None:
    client = _client()

    with client:
        response = client.post(
            "/api/browser/expand",
            json={"endpoint": "opc.tcp://127.0.0.1:4840", "max_depth": 0},
        )

    assert response.status_code == 400
    assert "max_depth" in response.json()["detail"]


def test_browser_page_returns_react_app(tmp_path: Path) -> None:
    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<main>app</main>", encoding="utf-8")
    settings = _settings()
    runtime = SimulatorRuntime(settings, FakeServer(), sleep=long_sleep)
    client = TestClient(create_app(settings, runtime=runtime, static_dir=static_dir))

    with client:
        response = client.get("/browser")

    assert response.status_code == 200
    assert response.text == "<main>app</main>"


def _client() -> TestClient:
    settings = _settings()
    runtime = SimulatorRuntime(settings, FakeServer(), sleep=long_sleep)
    return TestClient(
        create_app(
            settings,
            runtime=runtime,
            public_web_url="http://phone.local:8000",
        )
    )


def _settings() -> SimulatorSettings:
    return SimulatorSettings(
        server=ServerSettings(endpoint="opc.tcp://127.0.0.1:4840"),
        runtime=RuntimeSettings(update_interval_ms=1000),
        variables=(
            VariableDefinition("pump_running", "ns=2;s=pump_running", DataType.BOOLEAN, False),
            VariableDefinition(
                "status",
                "ns=2;s=status",
                DataType.STRING,
                "ready",
                writable=False,
            ),
            VariableDefinition(
                "wave",
                "ns=2;s=wave",
                DataType.FLOAT,
                1.0,
                generator=GeneratorSettings(kind="sine", amplitude=1.0, period_ticks=10),
            ),
        ),
    )
