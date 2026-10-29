"""The readings' update interval, which only this custom build lets be set.

Home Assistant core does not let integrations make their polling interval
configurable, so none of this is in core; the export copies this module in.

The interval is asked for while setting up and in the options. An interval
shorter than a poll takes is allowed, but warned about first: Home Assistant
starts the interval when a poll ends, so the meter is then read without pause,
and every update writes new states to the database.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, Final

import probatio

from homeassistant.config_entries import (
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import CONF_BAUDRATE

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

CONF_SCAN_INTERVAL: Final = "scan_interval"

DEFAULT_SCAN_INTERVAL: Final = 2.0
MIN_SCAN_INTERVAL: Final = 0.01
MAX_SCAN_INTERVAL: Final = 300.0

# What a poll of the default entities costs on the bus, to estimate its time
# before one has been measured: three reads (measurements, energy and the
# wiring check) of 52, 64 and 1 registers. A request is 8 bytes and an answer
# 5 bytes plus 2 per register, each byte 11 bits on the wire with start and
# stop bits.
DEFAULT_POLL_BITS: Final = (3 * 8 + (5 + 2 * 52) + (5 + 2 * 64) + (5 + 2 * 1)) * 11
DEFAULT_POLL_READS: Final = 3
# The time each read takes beyond its bits: the meter's turnaround and the
# link's. Measured on an EM540 behind an ESPHome serial proxy at 57600 baud,
# where a poll of the default entities took about 160 ms.
READ_OVERHEAD: Final = 0.036


def _seconds(value: Any) -> float:
    """Read an interval typed in seconds, with a decimal point or comma."""
    try:
        return float(str(value).strip().replace(",", "."))
    except ValueError as err:
        raise probatio.Invalid("enter a number of seconds, such as 2 or 0.5") from err


# A text field rather than a number box: the box's step buttons are no use
# across 0.01 to 300 seconds, and a decimal comma is welcome too.
INTERVAL_FIELD = {
    probatio.Required(
        CONF_SCAN_INTERVAL, default=f"{DEFAULT_SCAN_INTERVAL:g}"
    ): probatio.All(
        TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT, suffix="s")),
        _seconds,
        probatio.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
    ),
}
INTERVAL_SCHEMA = probatio.Schema(INTERVAL_FIELD)


def scan_interval(entry: ConfigEntry) -> timedelta:
    """Return how often an entry's readings are polled."""
    return timedelta(
        seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )


def with_interval(schema: probatio.Schema) -> probatio.Schema:
    """Add the update interval to a setup form."""
    return schema.extend(INTERVAL_FIELD)


def estimate_poll(baudrate: int) -> float:
    """Estimate how long a poll of the default entities takes, in seconds."""
    return DEFAULT_POLL_BITS / baudrate + DEFAULT_POLL_READS * READ_OVERHEAD


def _duration(seconds: float) -> str:
    """Format a duration the way the forms show it."""
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    return f"{seconds:.2f} s"


def _interval(seconds: float) -> str:
    """Format an interval without trailing zeros."""
    return f"{seconds:g} s"


def _suggested(seconds: float) -> dict[str, str]:
    """Fill the interval's text field in with a stored interval."""
    return {CONF_SCAN_INTERVAL: f"{seconds:g}"}


class IntervalFlowMixin(ConfigFlow):
    """Ask for the update interval while setting up, warning when it is short.

    The interval is kept in the entry's options, where the options flow
    changes it later; the rest of the setup form is entry data.
    """

    _pending_entry: dict[str, Any]

    async def async_create_entry_with_interval(
        self, *, title: str, data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Create the entry, or first warn about a short interval."""
        options = {CONF_SCAN_INTERVAL: data.pop(CONF_SCAN_INTERVAL)}
        self._pending_entry = {"title": title, "data": data, "options": options}
        return await self.async_step_interval_warning()

    async def async_step_interval_warning(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the pending entry, or warn when its interval is shorter than a poll."""
        pending = self._pending_entry
        interval = pending["options"][CONF_SCAN_INTERVAL]
        if (baudrate := pending["data"].get(CONF_BAUDRATE)) is None:
            # Behind a gateway the bus's baud rate is not known here; the
            # options show the measured poll time once the meter is set up.
            return self.async_create_entry(**pending)
        poll = estimate_poll(baudrate)
        if interval >= poll:
            return self.async_create_entry(**pending)
        return self.async_show_menu(
            step_id="interval_warning",
            menu_options=["interval_keep", "interval_change"],
            description_placeholders={
                "interval": _interval(interval),
                "poll": f"about {_duration(poll)}",
                "baudrate": str(baudrate),
            },
        )

    async def async_step_interval_keep(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set the meter up with the short interval after all."""
        return self.async_create_entry(**self._pending_entry)

    async def async_step_interval_change(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for another update interval."""
        if user_input is not None:
            self._pending_entry["options"] = user_input
            return await self.async_step_interval_warning()
        return self.async_show_form(
            step_id="interval_change",
            data_schema=self.add_suggested_values_to_schema(
                INTERVAL_SCHEMA,
                _suggested(self._pending_entry["options"][CONF_SCAN_INTERVAL]),
            ),
        )


class CarloGavazziModbusOptionsFlowHandler(OptionsFlowWithReload):
    """Set how often the readings are polled; the entry reloads on save."""

    _pending: dict[str, Any]

    def _poll(self) -> tuple[float | None, str]:
        """Return how long a poll takes, measured or estimated, and how to say it."""
        if self.config_entry.state is ConfigEntryState.LOADED:
            measured = self.config_entry.runtime_data.readings.last_poll_duration
            if measured is not None:
                seconds = measured.total_seconds()
                return seconds, f"{_duration(seconds)}, the last poll"
        if (baudrate := self.config_entry.data.get(CONF_BAUDRATE)) is not None:
            seconds = estimate_poll(baudrate)
            return seconds, f"about {_duration(seconds)}, estimated for {baudrate} baud"
        return None, "unknown"

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the update interval, showing how long a poll takes."""
        poll, poll_text = self._poll()
        if user_input is not None:
            if poll is None or user_input[CONF_SCAN_INTERVAL] >= poll:
                return self.async_create_entry(data=user_input)
            self._pending = user_input
            return await self.async_step_warning()
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                INTERVAL_SCHEMA,
                _suggested(
                    self.config_entry.options.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    )
                ),
            ),
            description_placeholders={"duration": poll_text},
        )

    async def async_step_warning(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Warn that the interval is shorter than a poll takes."""
        return self.async_show_menu(
            step_id="warning",
            menu_options=["keep", "init"],
            description_placeholders={
                "interval": _interval(self._pending[CONF_SCAN_INTERVAL]),
                "poll": self._poll()[1],
            },
        )

    async def async_step_keep(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Save the short interval after all."""
        return self.async_create_entry(data=self._pending)
