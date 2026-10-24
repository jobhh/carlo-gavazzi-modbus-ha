# Carlo Gavazzi Modbus for Home Assistant

A custom integration for Carlo Gavazzi energy meters on RS485, read over
Modbus RTU:

- **EM500 series:** EM530 and EM540, including the MID variants Victron sells.
- **EM300/ET300 series:** EM330, EM340, ET330 and ET340.

The meter's bus can be reached through a serial port, an ESPHome serial
proxy, or an RS485-to-TCP gateway in transparent mode.

This is a test build of the `carlo_gavazzi_modbus` integration being prepared
for Home Assistant core. It is exported from that work with
`tools/export_from_core.py`; `SOURCE` names the core commit. It talks to the
meter through the
[carlo-gavazzi-energy-meter-modbus](https://pypi.org/project/carlo-gavazzi-energy-meter-modbus/)
library, which Home Assistant installs from PyPI when it loads the integration.

## Requirements

- Home Assistant **2026.10.0 or newer**. The integration borrows its Modbus
  connection from the built-in `modbus` integration, which gained the API it
  needs in that release. It is tested on 2026.10.2.
- One Modbus master on the bus. Stop anything else that polls the meter, such
  as an ESPHome `modbus_controller` on the same port.
- Internet access the first time Home Assistant loads the integration, to
  install the library.

## Install

Copy `custom_components/carlo_gavazzi_modbus` into the `custom_components`
folder of your Home Assistant configuration (create it if it does not exist),
so you end up with `/config/custom_components/carlo_gavazzi_modbus/manifest.json`.
The Samba, SSH or Studio Code Server add-ons all work for this. Then restart
Home Assistant.

With HACS: add this repository as a custom repository of type *Integration*,
install *Carlo Gavazzi Modbus*, and restart.

## Set up

1. **Settings → Devices & services → Add integration → Carlo Gavazzi Modbus.**
2. Pick how the meter's bus is reached. For a meter behind an ESPHome serial
   proxy, choose *Serial port or ESPHome serial proxy*.
3. Pick the serial port. ESPHome serial proxies are listed with the ESPHome
   device's port name, such as *KC868-A16 RS-485*.
4. Enter the **baud rate** set on the meter (the meter shows it under
   *rS485*). The **Modbus address** is under *More options*; leave it at 1
   unless you changed it on the meter.

The integration reads the meter's identity, checks the model, and creates a
device with its sensors. Some sensors, such as per-phase THD, are disabled by
default; enable them on the device page.

After changing the baud rate or address on the meter, open the integration's
menu and choose **Reconfigure** to enter the new settings.

## Update interval

The readings (power, energy, status) are polled every 5 seconds. To change
that, open the integration's **Configure** dialog and set the update interval,
from 1 to 300 seconds. Use 1 second for something like battery control. This
option exists only in this custom build: Home Assistant core does not let
integrations make their polling interval configurable.

Measured on an EM540 (firmware 1.4.3) behind a wired ESPHome serial proxy:

| Baud rate | One full readings poll |
| --- | --- |
| 9600 | about 1.05 s |
| 38400 | about 0.56 s |
| 57600 | about 0.51 s |
| 115200 | about 0.45 s |

The meter refreshes its values every 80 ms. At 9600 baud a full poll takes
longer than a second, so for a 1-second interval set the meter to 38400 baud
or faster.

## Good to know

- **Wiring error** (`binary_sensor.<meter>_wiring_error`) is the meter's own
  wrong-connection flag. It also turns on when one phase exports while the
  others import, such as with a single-phase solar inverter or battery. If
  that is your installation, the flag is not a wiring problem.
- **Reset buttons** for the partial counters, the demand values and the tariff
  counters write to the meter when pressed. The lifetime totals cannot be
  reset from Home Assistant.
- Negative power means export.
- Diagnostics (on the device page) include a fresh read of every register the
  meter serves, with the serial number left out. Attach them to an issue.

## Develop

The tests run against Home Assistant 2026.10.2 and need Linux (or WSL):

```bash
uv sync
uv run pytest
```

`tests/test_live.py` sets the integration up against a real meter, through the
real config flow. It only reads, and it is skipped unless you name the port:

```bash
CG_LIVE_DEVICE='esphome://<host>/?port_name=<name>&noise_psk=<key>' \
CG_LIVE_BAUDRATE=57600 uv run pytest tests/test_live.py -s
```

To update this build from a core checkout that has the integration on its
branch, generate the translations there, then export:

```bash
python tools/export_from_core.py ../core
uv run pytest --snapshot-update
```

The snapshot update is needed because 2026.10 records entity registry entries
slightly differently from core's development branch.
