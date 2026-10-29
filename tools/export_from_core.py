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
VERSION = "0.7.0"

ROOT = Path(__file__).parent.parent
TARGET = ROOT / "custom_components" / DOMAIN
TESTS = ROOT / "tests"
OVERLAY = ROOT / "tools" / "overlay"
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
    # The brand images are this repository's own; core keeps them in the
    # brands repository instead.
    for path in TARGET.iterdir() if TARGET.exists() else ():
        if path.name == "brand":
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    shutil.copytree(
        source,
        TARGET,
        ignore=shutil.ignore_patterns(
            "__pycache__", "strings.json", "quality_scale.yaml"
        ),
        dirs_exist_ok=True,
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
    # At the end of setting up, which reaches past the platforms' setup.
    replace(
        init,
        "\n\nasync def async_unload_entry(",
        "    return True\n\n\nasync def async_unload_entry(",
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
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Use Home Assistant's snapshot format.

    The custom-component plugin overrides syrupy's fixture too, but which of
    the two wins depends on the order the plugins load in.
    """
    return snapshot.use_extension(HomeAssistantSnapshotExtension)


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
    replace(
        conftest,
        "from pytest_homeassistant_custom_component.common import MockConfigEntry\n",
        "from pytest_homeassistant_custom_component.common import MockConfigEntry\n"
        "from pytest_homeassistant_custom_component.syrupy import (\n"
        "    HomeAssistantSnapshotExtension,\n"
        ")\n"
        "from syrupy.assertion import SnapshotAssertion\n",
    )


def add_update_interval_option() -> None:
    """Let the update interval be set, which core does not allow.

    The logic lives in ``tools/overlay/interval.py``; this copies it in and
    hooks it into the coordinator and the config flow.
    """
    shutil.copy(OVERLAY / "interval.py", TARGET / "interval.py")

    coordinator = TARGET / "coordinator.py"
    replace(
        coordinator,
        "from .const import DOMAIN, LOGGER, SCAN_INTERVAL, SETTINGS_SCAN_INTERVAL\n",
        "from .const import DOMAIN, LOGGER, SETTINGS_SCAN_INTERVAL\n"
        "from .interval import scan_interval\n",
    )
    replace(
        coordinator,
        "        interval=SCAN_INTERVAL,\n",
        "        interval=scan_interval(entry),\n",
    )

    flow = TARGET / "config_flow.py"
    replace(
        flow,
        "from homeassistant.exceptions import HomeAssistantError\n",
        "from homeassistant.core import callback\n"
        "from homeassistant.exceptions import HomeAssistantError\n",
    )
    replace(
        flow,
        "from .helpers import async_setup_meter, create_modbus_params\n",
        "from .helpers import async_setup_meter, create_modbus_params\n"
        "from .interval import (\n"
        "    CarloGavazziModbusOptionsFlowHandler,\n"
        "    IntervalFlowMixin,\n"
        "    with_interval,\n"
        ")\n",
    )
    replace(
        flow,
        "class CarloGavazziModbusFlowHandler(ConfigFlow, domain=DOMAIN):\n",
        "class CarloGavazziModbusFlowHandler(IntervalFlowMixin, domain=DOMAIN):\n",
    )
    replace(
        flow,
        "                return self.async_create_entry(title=meter_name(meter), data=data)\n",
        "                return await self.async_create_entry_with_interval(\n"
        "                    title=meter_name(meter), data=data\n"
        "                )\n",
    )
    replace(
        flow,
        "            data_schema=self.add_suggested_values_to_schema(schema, suggested_values),\n",
        "            data_schema=self.add_suggested_values_to_schema(\n"
        "                with_interval(schema), suggested_values\n"
        "            ),\n",
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

    translations = TARGET / "translations" / "en.json"
    data = json.loads(translations.read_text())
    steps = data["config"]["step"]
    for step in ("serial_baudrate", "serial_baudrate_unknown", "gateway"):
        steps[step]["data"]["scan_interval"] = INTERVAL_LABEL
        steps[step]["data_description"]["scan_interval"] = INTERVAL_DESCRIPTION
    steps["interval_warning"] = {
        "title": WARNING_TITLE,
        "description": WARNING_DESCRIPTION.format(poll="{poll} at {baudrate} baud"),
        "menu_options": {
            "interval_keep": KEEP_LABEL,
            "interval_change": CHANGE_LABEL,
        },
    }
    steps["interval_change"] = {
        "title": "Update interval",
        "data": {"scan_interval": INTERVAL_LABEL},
        "data_description": {"scan_interval": INTERVAL_DESCRIPTION},
    }
    data["options"] = {
        "step": {
            "init": {
                "title": "Update interval",
                "description": (
                    "A poll of this meter takes {duration}. Enabling more"
                    " entities makes a poll take longer."
                ),
                "data": {"scan_interval": INTERVAL_LABEL},
                "data_description": {"scan_interval": INTERVAL_DESCRIPTION},
            },
            "warning": {
                "title": WARNING_TITLE,
                "description": WARNING_DESCRIPTION.format(poll="{poll}"),
                "menu_options": {"keep": KEEP_LABEL, "init": CHANGE_LABEL},
            },
        }
    }
    translations.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", newline="\n"
    )


INTERVAL_LABEL = "Update interval"
INTERVAL_DESCRIPTION = (
    "How often power, energy and the meter's status are read, in seconds:"
    " anything from 0.01 to 300, such as 2 or 0.5. The default is 2. Use 1 or"
    " less for something like battery control.\n\n"
    "Reading the default sensors takes about 0.42 s at 9600 baud, 0.19 s at"
    " 38400 and 0.16 s at 57600. A shorter interval than that does not make"
    " updates faster; if yours is shorter, you are warned after selecting"
    " Submit."
)
WARNING_TITLE = "Short update interval"
WARNING_DESCRIPTION = (
    "You set the readings to update every {{interval}}, but a poll of the"
    " meter takes {poll}.\n\n"
    "- Updates will not come faster than a poll takes. Home Assistant starts"
    " the interval when a poll ends, so the meter is read without pause, and"
    " other devices on the same bus wait longer for their turn.\n"
    "- Home Assistant records a new state each time a value changes. Power,"
    " current and voltage change on almost every read, so at this rate they"
    " add many rows to the database. Consider excluding the sensors you do"
    " not need from the recorder.\n\n"
    "Raising the baud rate on the meter, and then here with Reconfigure,"
    " makes a poll quicker."
)
KEEP_LABEL = "Keep this interval"
CHANGE_LABEL = "Change the interval"


def adapt_manifest() -> None:
    """Point the manifest at this repository and give it a version."""
    path = TARGET / "manifest.json"
    manifest = json.loads(path.read_text())
    # Hassfest's schema for custom integrations does not know categories yet.
    del manifest["categories"]
    manifest["documentation"] = REPO
    manifest["issue_tracker"] = f"{REPO}/issues"
    manifest["version"] = VERSION
    # Core's own keys; a custom integration has no quality scale.
    manifest.pop("quality_scale", None)
    # Hassfest wants domain and name first, then the rest in order.
    first = {key: manifest.pop(key) for key in ("domain", "name")}
    manifest = first | dict(sorted(manifest.items()))
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
