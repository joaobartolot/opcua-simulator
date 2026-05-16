from src.domain.models import DataType, RuntimeSettings, ServerSettings, SimulatorSettings, VariableDefinition
from src.main import simulator_main, web_main


def test_simulator_main_loads_selected_config(monkeypatch) -> None:
    settings = SimulatorSettings(
        server=ServerSettings(),
        runtime=RuntimeSettings(),
        variables=(
            VariableDefinition("status", "ns=2;s=status", DataType.STRING, "ready"),
        ),
    )
    calls = []

    def settings_loader(config_path):
        calls.append(config_path)
        return settings

    def simulator_runner(loaded_settings):
        calls.append(loaded_settings)

    exit_code = simulator_main(
        ["--config", "custom.yaml"],
        settings_loader=settings_loader,
        simulator_runner=simulator_runner,
    )

    assert exit_code == 0
    assert str(calls[0]) == "custom.yaml"
    assert calls[1] is settings


def test_web_main_loads_selected_config_and_runs_uvicorn() -> None:
    settings = SimulatorSettings(
        server=ServerSettings(),
        runtime=RuntimeSettings(),
        variables=(
            VariableDefinition("status", "ns=2;s=status", DataType.STRING, "ready"),
        ),
    )
    calls = []

    def settings_loader(config_path):
        calls.append(config_path)
        return settings

    def uvicorn_runner(app, **kwargs):
        calls.append(kwargs)

    exit_code = web_main(
        ["--config", "web.yaml", "--host", "127.0.0.1", "--port", "9000"],
        settings_loader=settings_loader,
        uvicorn_runner=uvicorn_runner,
    )

    assert exit_code == 0
    assert str(calls[0]) == "web.yaml"
    assert calls[1]["host"] == "127.0.0.1"
    assert calls[1]["port"] == 9000


def test_web_main_ignores_generic_web_port_environment(monkeypatch) -> None:
    monkeypatch.setenv("WEB_PORT", "8080")
    settings = SimulatorSettings(
        server=ServerSettings(),
        runtime=RuntimeSettings(),
        variables=(
            VariableDefinition("status", "ns=2;s=status", DataType.STRING, "ready"),
        ),
    )
    calls = []

    def settings_loader(config_path):
        return settings

    def uvicorn_runner(app, **kwargs):
        calls.append(kwargs)

    exit_code = web_main(
        [],
        settings_loader=settings_loader,
        uvicorn_runner=uvicorn_runner,
    )

    assert exit_code == 0
    assert calls[0]["port"] == 8000


def test_web_main_rejects_opcua_endpoint_port_conflict(capsys) -> None:
    settings = SimulatorSettings(
        server=ServerSettings(endpoint="opc.tcp://0.0.0.0:8000"),
        runtime=RuntimeSettings(),
        variables=(
            VariableDefinition("status", "ns=2;s=status", DataType.STRING, "ready"),
        ),
    )

    def settings_loader(config_path):
        return settings

    def uvicorn_runner(app, **kwargs):
        raise AssertionError("web server should not start with a conflicting OPC UA port")

    exit_code = web_main(
        ["--port", "8000"],
        settings_loader=settings_loader,
        uvicorn_runner=uvicorn_runner,
    )

    assert exit_code == 2
    assert "web port conflicts with the OPC UA endpoint port" in capsys.readouterr().err
