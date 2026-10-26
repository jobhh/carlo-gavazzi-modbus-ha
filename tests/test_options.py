"""Tests for the update interval option, which only this custom build has."""

from datetime import timedelta

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.carlo_gavazzi_modbus.const import (
    CONF_SCAN_INTERVAL,
    SCAN_INTERVAL,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType


async def test_default_update_interval(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the readings are polled at the default interval without options."""
    coordinator = init_integration.runtime_data.readings
    assert coordinator.update_interval == SCAN_INTERVAL


async def test_options_of_an_unloaded_entry(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test the options can be set while the meter is not set up."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["description_placeholders"] == {"duration": "unknown"}


async def test_options_set_the_update_interval(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the options set the readings interval, and reload the entry."""
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    # The form says how long the first poll took.
    assert result["description_placeholders"]["duration"].endswith(" ms")

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 1}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert init_integration.options == {CONF_SCAN_INTERVAL: 1}
    assert init_integration.state is ConfigEntryState.LOADED
    coordinator = init_integration.runtime_data.readings
    assert coordinator.update_interval == timedelta(seconds=1)
