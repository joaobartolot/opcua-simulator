from src.domain.models import DataType, RuntimeSettings, ServerSettings, SimulatorSettings, VariableDefinition
from src.main import simulator_main


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
