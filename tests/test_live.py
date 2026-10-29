"""Set up the integration against a real meter, through the real config flow.

Skipped unless ``CG_LIVE_DEVICE`` names the meter's serial port, for example
an ESPHome serial proxy::

    CG_LIVE_DEVICE='esphome://host/?port_name=RS485&noise_psk=...' \\
    CG_LIVE_BAUDRATE=57600 pytest tests/test_live.py

Everything it does is a read. It never writes to the meter.
"""

import os
import re
from urllib.parse import urlsplit

import pytest
import pytest_socket

from custom_components.carlo_gavazzi_modbus.config_flow import SECTION_MORE_OPTIONS
from custom_components.carlo_gavazzi_modbus.const import (
    CONF_BAUDRATE,
    CONF_UNIT_ID,
    DOMAIN,
    TYPE_SERIAL,
)
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_DEVICE, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

LIVE_DEVICE = os.environ.get("CG_LIVE_DEVICE")

pytestmark = [
    pytest.mark.skipif(not LIVE_DEVICE, reason="set CG_LIVE_DEVICE to run"),
    pytest.mark.enable_socket,
]


@pytest.fixture
def mock_shared_connection() -> None:
    """Use the real connection, not the mock meter every other test gets."""


@pytest.fixture(autouse=True)
def allow_meter_host() -> None:
    """Let the test reach the meter's host; the harness allows only 127.0.0.1."""
    host = urlsplit(LIVE_DEVICE or "").hostname
    if host:
        pytest_socket.socket_allow_hosts(["127.0.0.1", host])


@pytest.fixture
def expected_lingering_tasks() -> bool:
    """The real serial link may still be closing when the test ends."""
    return True


@pytest.fixture
def expected_lingering_timers() -> bool:
    """The real serial link may still be closing when the test ends."""
    return True


async def test_live_meter(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Test a real meter configures, sets up and reports plausible readings."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": TYPE_SERIAL}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE: LIVE_DEVICE,
            SECTION_MORE_OPTIONS: {
                CONF_UNIT_ID: int(os.environ.get("CG_LIVE_UNIT_ID", "1"))
            },
        },
    )
    # Home Assistant looked for the meter's baud rate on the port.
    assert result["step_id"] == "serial_baudrate", result
    assert result["errors"] == {}, result
    baudrate = next(
        key for key in result["data_schema"].schema if key == CONF_BAUDRATE
    ).description["suggested_value"]
    print(f"\ndetected baud rate: {baudrate}")
    if expected := os.environ.get("CG_LIVE_BAUDRATE"):
        assert baudrate == expected
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BAUDRATE: baudrate}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY, result
    await hass.async_block_till_done()

    entry = result["result"]
    assert entry.state is ConfigEntryState.LOADED
    coordinator = entry.runtime_data.readings
    meter = coordinator.meter
    assert meter.model is not None
    print(f"\n{meter.model.name} {meter.firmware_version}")
    print(f"first poll, every block: {coordinator.last_poll_duration}")

    # The first poll ran before the entities said what they show; time a few
    # polls of just that.
    durations = []
    for _ in range(5):
        await coordinator.async_refresh()
        assert coordinator.last_poll_duration is not None
        durations.append(coordinator.last_poll_duration.total_seconds() * 1000)
    print(
        "polls of what the enabled entities show:", [f"{d:.0f} ms" for d in durations]
    )

    # The settings are read at setup; read them once more the way their slow
    # poll does.
    settings = entry.runtime_data.settings
    await settings.async_refresh()
    assert settings.last_update_success
    assert settings.data.updated == {"settings"}
    print(f"settings poll: {settings.last_poll_duration}")

    states = {
        entity.entity_id: hass.states.get(entity.entity_id)
        for entity in er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    }
    available = {
        entity_id: state.state
        for entity_id, state in states.items()
        if state is not None and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)
    }
    for entity_id, value in sorted(available.items()):
        print(f"  {entity_id}: {value}")
    assert available, "no entity has a value"

    voltages = [
        float(value)
        for entity_id, value in available.items()
        if re.fullmatch(r"sensor\.\w+_voltage_l[123]", entity_id)
    ]
    assert voltages
    assert all(200 < voltage < 260 for voltage in voltages), voltages

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
