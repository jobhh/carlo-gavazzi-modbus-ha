"""Tests for the update interval, which only this custom build lets be set."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.carlo_gavazzi_modbus.config_flow import SECTION_MORE_OPTIONS
from custom_components.carlo_gavazzi_modbus.const import (
    CONF_BAUDRATE,
    CONF_UNIT_ID,
    DOMAIN,
)
from custom_components.carlo_gavazzi_modbus.interval import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    estimate_poll,
)
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData

from .conftest import BAUDRATE, DEVICE, SERIAL_NUMBER, UNIT_ID


async def _submit_serial(hass: HomeAssistant, **overrides: object) -> dict:
    """Set up on the serial port, submitting the baud rate step with overrides."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "serial"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_DEVICE: DEVICE, SECTION_MORE_OPTIONS: {CONF_UNIT_ID: UNIT_ID}},
    )
    # The interval is asked for with the baud rate.
    assert result["step_id"] == "serial_baudrate"
    assert CONF_SCAN_INTERVAL in result["data_schema"].schema
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BAUDRATE: str(BAUDRATE), **overrides}
    )


def test_estimate_poll() -> None:
    """Test the estimate matches the poll measured at 57600 baud, about 160 ms.

    The field's description quotes these figures.
    """
    assert estimate_poll(57600) == pytest.approx(0.16, abs=0.005)
    assert estimate_poll(38400) == pytest.approx(0.19, abs=0.005)
    assert estimate_poll(9600) == pytest.approx(0.42, abs=0.005)


async def test_default_update_interval(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the readings are polled every 2 seconds without options."""
    coordinator = init_integration.runtime_data.readings
    assert coordinator.update_interval == timedelta(seconds=DEFAULT_SCAN_INTERVAL)


@pytest.mark.usefixtures("mock_setup_entry")
async def test_setup_asks_for_the_interval(hass: HomeAssistant) -> None:
    """Test the interval set while setting up lands in the options."""
    result = await _submit_serial(hass, **{CONF_SCAN_INTERVAL: "1"})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == SERIAL_NUMBER
    assert CONF_SCAN_INTERVAL not in result["data"]
    assert result["options"] == {CONF_SCAN_INTERVAL: 1.0}


@pytest.mark.usefixtures("mock_setup_entry")
async def test_setup_takes_a_decimal_comma(hass: HomeAssistant) -> None:
    """Test an interval typed with a decimal comma is read as seconds."""
    result = await _submit_serial(hass, **{CONF_SCAN_INTERVAL: "1,5"})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == SERIAL_NUMBER
    assert result["options"] == {CONF_SCAN_INTERVAL: 1.5}


@pytest.mark.parametrize("interval", ["fast", "0", "301"])
async def test_setup_refuses_an_invalid_interval(
    hass: HomeAssistant, interval: str
) -> None:
    """Test an interval that is no number of seconds in range is refused."""
    with pytest.raises(InvalidData):
        await _submit_serial(hass, **{CONF_SCAN_INTERVAL: interval})


@pytest.mark.usefixtures("mock_setup_entry")
async def test_setup_defaults_to_2_seconds(hass: HomeAssistant) -> None:
    """Test the interval defaults to 2 seconds."""
    result = await _submit_serial(hass)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == SERIAL_NUMBER
    assert result["options"] == {CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL}


@pytest.mark.usefixtures("mock_setup_entry")
async def test_setup_warns_about_a_short_interval(hass: HomeAssistant) -> None:
    """Test an interval shorter than a poll warns, and can be kept."""
    result = await _submit_serial(hass, **{CONF_SCAN_INTERVAL: "0.01"})

    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "interval_warning"
    assert result["description_placeholders"] == {
        "interval": "0.01 s",
        "poll": "about 160 ms",
        "baudrate": str(BAUDRATE),
    }

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "interval_keep"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == SERIAL_NUMBER
    assert result["options"] == {CONF_SCAN_INTERVAL: 0.01}


@pytest.mark.usefixtures("mock_setup_entry")
async def test_setup_warning_lets_the_interval_change(hass: HomeAssistant) -> None:
    """Test the warning offers another interval, which is checked again."""
    result = await _submit_serial(hass, **{CONF_SCAN_INTERVAL: "0.01"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "interval_change"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "interval_change"

    # Still too short: warned again.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: "0.1"}
    )
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "interval_change"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: "0.5"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == SERIAL_NUMBER
    assert result["options"] == {CONF_SCAN_INTERVAL: 0.5}


@pytest.mark.usefixtures("mock_setup_entry")
async def test_setup_behind_a_gateway_does_not_warn(hass: HomeAssistant) -> None:
    """Test a gateway's unknown baud rate leaves the interval unchecked."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "gateway"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "gateway.local",
            CONF_PORT: 502,
            SECTION_MORE_OPTIONS: {CONF_UNIT_ID: UNIT_ID},
            CONF_SCAN_INTERVAL: "0.01",
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == SERIAL_NUMBER
    assert result["options"] == {CONF_SCAN_INTERVAL: 0.01}


async def test_options_of_an_unloaded_entry(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test the options estimate the poll time while the meter is not set up."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["description_placeholders"] == {
        "duration": f"about 160 ms, estimated for {BAUDRATE} baud"
    }


async def test_options_set_the_update_interval(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the options set the readings interval, and reload the entry."""
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    # The form says how long the last poll took.
    assert result["description_placeholders"]["duration"].endswith(", the last poll")

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: "1"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert init_integration.options == {CONF_SCAN_INTERVAL: 1.0}
    assert init_integration.state is ConfigEntryState.LOADED
    coordinator = init_integration.runtime_data.readings
    assert coordinator.update_interval == timedelta(seconds=1)


async def test_options_warn_about_a_short_interval(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test an interval shorter than the last poll warns, and can be kept."""
    coordinator = init_integration.runtime_data.readings
    with patch.object(coordinator, "last_poll_duration", timedelta(seconds=0.5)):
        result = await hass.config_entries.options.async_init(init_integration.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SCAN_INTERVAL: "0.25"}
        )
        assert result["type"] is FlowResultType.MENU
        assert result["step_id"] == "warning"
        assert result["description_placeholders"] == {
            "interval": "0.25 s",
            "poll": "500 ms, the last poll",
        }

        # Going back shows the form again.
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "init"}
        )
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SCAN_INTERVAL: "0.25"}
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "keep"}
        )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert init_integration.options == {CONF_SCAN_INTERVAL: 0.25}
