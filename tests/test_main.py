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
