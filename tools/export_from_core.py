"""Build this custom integration from the integration in a Home Assistant core checkout.

    python tools/export_from_core.py ../core

The core checkout has the ``carlo_gavazzi_modbus`` integration on its branch,
with its translations generated (``python3 -m script.translations develop
--integration carlo_gavazzi_modbus``). The integration and its tests are copied
over, then changed in three ways:

- for the Home Assistant release this build targets, which is older than core's
  development branch;
- to load from ``custom_components`` and test against
  ``pytest-homeassistant-custom-component``;
- with what only this build has: an option to set the update interval.

Every change asserts that the code it changes is still there, so a change in
core that this script does not know about stops the export instead of slipping
through.
"""

import json
from pathlib import Path
import shutil
import subprocess
import sys

DOMAIN = "carlo_gavazzi_modbus"
REPO = "https://github.com/jobhh/carlo-gavazzi-modbus-ha"
VERSION = "0.4.1"

ROOT = Path(__file__).parent.parent
TARGET = ROOT / "custom_components" / DOMAIN
TESTS = ROOT / "tests"
TOOLS = Path(__file__).parent


def replace(path: Path, old: str, new: str, count: int = 1) -> None:
    """Replace ``old`` in a file, which must occur exactly ``count`` times."""
    text = path.read_text()
    found = text.count(old)
    if found != count:
        raise SystemExit(f"{path}: expected {count} of {old!r}, found {found}")
    path.write_text(text.replace(old, new), newline="\n")


def copy_integration(core: Path) -> None:
    """Copy the integration, with the generated translations in place of strings.json."""
    source = core / "homeassistant" / "components" / DOMAIN
    if not (source / "translations" / "en.json").exists():
        raise SystemExit("generate the translations in core first")
    shutil.rmtree(TARGET, ignore_errors=True)
    shutil.copytree(
        source,
        TARGET,
        ignore=shutil.ignore_patterns(
            "__pycache__", "strings.json", "quality_scale.yaml"
        ),
    )


def copy_tests(core: Path) -> None:
    """Copy the tests, keeping this repository's own test files."""
    source = core / "tests" / "components" / DOMAIN
    own = {"test_live.py", "test_options.py"}
    for path in TESTS.iterdir():
        if path.name in own:
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    for path in source.iterdir():
        if path.name == "__pycache__":
            continue
        if path.is_dir():
            shutil.copytree(path, TESTS / path.name)
        else:
            shutil.copy2(path, TESTS / path.name)

    for path in TESTS.glob("*.py"):
        if path.name in own:
            continue
        text = path.read_text()
        text = text.replace(
            f"homeassistant.components.{DOMAIN}", f"custom_components.{DOMAIN}"
        )
        text = text.replace(
            "pytest_homeassistant.", "pytest_homeassistant_custom_component."
        )
        path.write_text(text, newline="\n")
    for path in (TESTS / "snapshots").glob("*.ambr"):
        text = path.read_text().replace(
            f"homeassistant.components.{DOMAIN}", f"custom_components.{DOMAIN}"
        )
        path.write_text(text, newline="\n")


def target_release() -> None:
    """Change what core's development branch has and 2026.10 does not."""
    init = TARGET / "__init__.py"
    # Setting up and unloading still report success as a boolean.
    replace(
        init,
        "    hass: HomeAssistant, entry: CarloGavazziModbusConfigEntry\n) -> None:\n"
        '    """Set up Carlo Gavazzi Modbus from a config entry."""',
        "    hass: HomeAssistant, entry: CarloGavazziModbusConfigEntry\n) -> bool:\n"
        '    """Set up Carlo Gavazzi Modbus from a config entry."""',
    )
    replace(
        init,
        "    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)\n",
        "    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)\n"
        "    return True\n",
    )
    replace(
        init,
        "    hass: HomeAssistant, entry: CarloGavazziModbusConfigEntry\n) -> None:\n"
        '    """Unload a Carlo Gavazzi Modbus config entry."""\n'
        "    await hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)\n",
        "    hass: HomeAssistant, entry: CarloGavazziModbusConfigEntry\n) -> bool:\n"
        '    """Unload a Carlo Gavazzi Modbus config entry."""\n'
        "    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)\n",
    )
    replace(
        TESTS / "conftest.py",
        "        return_value=None,\n",
        "        return_value=True,\n",
    )

    # The custom-component test package looks for fixtures next to the frame
    # that calls it, which is an executor thread here; read them by path.
    replace(
        TESTS / "conftest.py",
        "    fixture = await async_load_json_object_fixture(hass, meter, DOMAIN)\n",
        '    path = Path(__file__).parent / "fixtures" / meter\n'
        "    fixture = json.loads(await hass.async_add_executor_job(path.read_text))\n",
    )
    replace(
        TESTS / "conftest.py",
        "from pytest_homeassistant_custom_component.common import "
        "MockConfigEntry, async_load_json_object_fixture\n",
        "from pytest_homeassistant_custom_component.common import MockConfigEntry\n",
    )
    replace(
        TESTS / "conftest.py",
        "from contextlib import asynccontextmanager\n",
        "from contextlib import asynccontextmanager\nimport json\nfrom pathlib import Path\n",
    )

    # Core's test harness provides this fixture; the custom-component one does not.
    conftest = TESTS / "conftest.py"
    conftest.write_text(
        conftest.read_text()
        + '''

@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load the integration from custom_components."""


@pytest.fixture
def entity_registry_enabled_by_default() -> Generator[None]:
    """Enable every entity, including the ones disabled by default."""
    with patch(
        "homeassistant.helpers.entity.Entity.entity_registry_enabled_default",
        return_value=True,
        new_callable=PropertyMock,
    ):
        yield
''',
        newline="\n",
    )
    replace(
        conftest,
        "from unittest.mock import AsyncMock, patch\n",
        "from unittest.mock import AsyncMock, PropertyMock, patch\n",
    )


def add_update_interval_option() -> None:
    """Let the update interval be set, which core does not allow."""
    replace(
        TARGET / "const.py",
        "# A full poll takes about a second at the factory 9600 baud.\n"
        "SCAN_INTERVAL: Final = timedelta(seconds=5)\n",
        "# A full poll takes about a second at the factory 9600 baud.\n"
        "SCAN_INTERVAL: Final = timedelta(seconds=5)\n"
        "\n"
        "# How often the readings are polled, set in the options. A meter steering a\n"
        "# battery needs a reading every second or faster.\n"
        'CONF_SCAN_INTERVAL: Final = "scan_interval"\n'
        "MIN_SCAN_INTERVAL: Final = 1\n"
        "MAX_SCAN_INTERVAL: Final = 300\n",
    )

    coordinator = TARGET / "coordinator.py"
    replace(
        coordinator,
        "from .const import DOMAIN, LOGGER, SCAN_INTERVAL, SETTINGS_SCAN_INTERVAL\n",
        "from .const import (\n"
        "    CONF_SCAN_INTERVAL,\n"
        "    DOMAIN,\n"
        "    LOGGER,\n"
        "    SCAN_INTERVAL,\n"
        "    SETTINGS_SCAN_INTERVAL,\n"
        ")\n",
    )
    replace(
        coordinator,
        "        interval=SCAN_INTERVAL,\n",
        "        interval=timedelta(\n"
        "            seconds=entry.options.get(\n"
        "                CONF_SCAN_INTERVAL, SCAN_INTERVAL.total_seconds()\n"
        "            )\n"
        "        ),\n",
    )

    flow = TARGET / "config_flow.py"
    replace(
        flow,
        "from homeassistant.config_entries import (\n"
        "    ConfigEntry,\n"
        "    ConfigEntryState,\n"
        "    ConfigFlow,\n"
        "    ConfigFlowResult,\n"
        ")\n",
        "from homeassistant.config_entries import (\n"
        "    ConfigEntry,\n"
        "    ConfigEntryState,\n"
        "    ConfigFlow,\n"
        "    ConfigFlowResult,\n"
        "    OptionsFlowWithReload,\n"
        ")\n",
    )
    replace(
        flow,
        "from homeassistant.exceptions import HomeAssistantError\n",
        "from homeassistant.core import callback\n"
        "from homeassistant.exceptions import HomeAssistantError\n",
    )
    replace(
        flow,
        "    CONF_BAUDRATE,\n    CONF_UNIT_ID,\n",
        "    CONF_BAUDRATE,\n    CONF_SCAN_INTERVAL,\n    CONF_UNIT_ID,\n",
    )
    replace(
        flow,
        "    DOMAIN,\n    TYPE_GATEWAY,\n",
        "    DOMAIN,\n"
        "    MAX_SCAN_INTERVAL,\n"
        "    MIN_SCAN_INTERVAL,\n"
        "    SCAN_INTERVAL,\n"
        "    TYPE_GATEWAY,\n",
    )
    replace(
        flow,
        "SCHEMAS = {TYPE_SERIAL: STEP_SERIAL, TYPE_GATEWAY: STEP_GATEWAY}\n",
        "SCHEMAS = {TYPE_SERIAL: STEP_SERIAL, TYPE_GATEWAY: STEP_GATEWAY}\n"
        "\n"
        "OPTIONS_SCHEMA = probatio.Schema(\n"
        "    {\n"
        "        probatio.Required(\n"
        "            CONF_SCAN_INTERVAL, default=int(SCAN_INTERVAL.total_seconds())\n"
        "        ): probatio.All(\n"
        "            NumberSelector(\n"
        "                NumberSelectorConfig(\n"
        "                    min=MIN_SCAN_INTERVAL,\n"
        "                    max=MAX_SCAN_INTERVAL,\n"
        "                    step=1,\n"
        "                    mode=NumberSelectorMode.BOX,\n"
        '                    unit_of_measurement="s",\n'
        "                )\n"
        "            ),\n"
        "            probatio.Coerce(int),\n"
        "        ),\n"
        "    }\n"
        ")\n",
    )
    replace(
        flow,
        "    VERSION = 1\n\n",
        "    VERSION = 1\n"
        "\n"
        "    @staticmethod\n"
        "    @callback\n"
        "    def async_get_options_flow(\n"
        "        config_entry: ConfigEntry,\n"
        "    ) -> CarloGavazziModbusOptionsFlowHandler:\n"
        '        """Return the options flow."""\n'
        "        return CarloGavazziModbusOptionsFlowHandler()\n"
        "\n",
    )
    flow.write_text(
        flow.read_text()
        + '''

class CarloGavazziModbusOptionsFlowHandler(OptionsFlowWithReload):
    """Set how often the readings are polled; the entry reloads on save."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the update interval, showing how long a poll takes."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        duration = "unknown"
        if self.config_entry.state is ConfigEntryState.LOADED:
            coordinator = self.config_entry.runtime_data.readings
            if coordinator.last_poll_duration is not None:
                milliseconds = coordinator.last_poll_duration.total_seconds() * 1000
                duration = f"{milliseconds:.0f} ms"
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
            description_placeholders={"duration": duration},
        )
''',
        newline="\n",
    )

    translations = TARGET / "translations" / "en.json"
    data = json.loads(translations.read_text())
    data["options"] = {
        "step": {
            "init": {
                "data": {"scan_interval": "Readings update interval"},
                "data_description": {
                    "scan_interval": (
                        "How often power, energy and the meter's status are read, in"
                        " seconds. Use 1 second for battery control; at 9600 baud a"
                        " full read takes about a second, so set the meter to 38400"
                        " baud or faster for that."
                    )
                },
                "description": (
                    "The last poll of this meter took {duration}. Polls queue up"
                    " behind each other, so set the interval longer than that."
                    " Enabling more entities makes a poll take longer."
                ),
                "title": "Update interval",
            }
        }
    }
    translations.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", newline="\n"
    )


def adapt_manifest() -> None:
    """Point the manifest at this repository and give it a version."""
    path = TARGET / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["documentation"] = REPO
    manifest["issue_tracker"] = f"{REPO}/issues"
    manifest["version"] = VERSION
    # Core's own keys; a custom integration has no quality scale.
    manifest.pop("quality_scale", None)
    path.write_text(json.dumps(manifest, indent=2) + "\n", newline="\n")


def record_source(core: Path) -> None:
    """Write which core commit this build was exported from."""
    commit = subprocess.run(
        ["git", "-C", str(core), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    branch = subprocess.run(
        ["git", "-C", str(core), "branch", "--show-current"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    (ROOT / "SOURCE").write_text(
        f"Exported from Home Assistant core, branch {branch}, commit {commit}.\n",
        newline="\n",
    )


def main(core: str) -> None:
    """Export the integration and its tests from a core checkout."""
    checkout = Path(core)
    copy_integration(checkout)
    copy_tests(checkout)
    target_release()
    add_update_interval_option()
    adapt_manifest()
    record_source(checkout)


if __name__ == "__main__":
    main(*sys.argv[1:])
