# Carlo Gavazzi Modbus for Home Assistant

Reads a Carlo Gavazzi energy meter, such as the EM540 or the ET340, over its
RS485 port. The meter measures what flows through it every second: power,
voltage and current per phase, and the energy you take from the grid and send
back to it. There is no account and no cloud service involved, and no other
software sits between Home Assistant and the meter.

These meters are often installed as the grid meter for a home battery or solar
system, for example with Victron Energy equipment. Home Assistant can read the
same kind of meter on a bus of its own.

This is a community project. It is not made, supported or endorsed by Carlo
Gavazzi; their name and logo are used only to say which meters it works with.

## Supported meters

- **EM530** and **EM540**, including their MID-certified variants.
- **EM330**, **EM340**, **ET330** and **ET340**, and the single-tariff
  **EM331** and **EM341**.

The integration has been tested with an EM540. The others are supported from
Carlo Gavazzi's Modbus protocol documents for each series.

Other Carlo Gavazzi meters, such as the EM100, EM210 and EM24 series, use
other register maps and are not supported. If setup finds one, it tells you
the model code the device reported.

## Requirements

- Home Assistant **2026.10.0 or newer**. The integration borrows its Modbus
  connection from the built-in `modbus` integration, which gained the API it
  needs in that release.
- A way to reach the meter's RS485 bus:
  - a USB-to-RS485 adapter on the machine running Home Assistant;
  - an [ESPHome](https://esphome.io/) device with an RS485 transceiver, set up
    as a serial proxy; or
  - an RS485-to-TCP gateway in **transparent** mode, which passes the RTU
    frames through unchanged. A gateway that converts to Modbus TCP is not
    supported.
- One device asking questions on the bus. Modbus RTU allows only one, so do
  not connect Home Assistant to a bus that something else already polls, such
  as a Victron GX device or an ESPHome `modbus_controller`.

## Install

**Home Assistant 2026.11 and newer:** add this repository in
**Settings → Marketplace** from its link, install *Carlo Gavazzi Modbus*, and
restart Home Assistant.

**With HACS, on 2026.10:** add this repository as a custom repository of type
*Integration*, install *Carlo Gavazzi Modbus*, and restart.

**By hand:** download the zip from the latest
[release](https://github.com/jobhh/carlo-gavazzi-modbus-ha/releases), and
unpack it into the `custom_components` folder of your configuration, so you
end up with `/config/custom_components/carlo_gavazzi_modbus/manifest.json`.
Then restart.

Home Assistant installs the
[carlo-gavazzi-energy-meter-modbus](https://pypi.org/project/carlo-gavazzi-energy-meter-modbus/)
library from PyPI the first time it loads the integration, so it needs
internet access then.

## Set up

Look up two settings in the meter's setup menu, on the page for its RS485 port
(*rS485*):

- the **Modbus address**: `1` unless it was changed. Every meter on one bus
  needs its own;
- the **baud rate**: `9600` unless it was changed. A faster rate, such as
  `38400` or `57600`, makes every poll quicker. Change it on the meter first.

The meters use 8 data bits, no parity and 1 stop bit out of the box, which is
what the integration uses.

Then go to **Settings → Devices & services → Add integration → Carlo Gavazzi
Modbus**, and pick how the bus is reached:

- **Serial port or ESPHome serial proxy:** pick the port, and enter the baud
  rate. ESPHome serial proxies are listed with the ESPHome device's port name.
- **RS485-to-TCP gateway:** enter the gateway's host and port (often `502`).
  Set the gateway's serial side to the meter's baud rate, 8N1.

The Modbus address is under **More options**.

To change these later, for example after changing the baud rate on the meter,
open the integration's menu and choose **Reconfigure**.

## What you get

The meter is added as a device. Home Assistant recognizes it by its serial
number, so moving it to another port or address does not create a second
device.

Which entities are added depends on the model and on how the meter is set up.
A meter wired without a neutral has no voltages against one. A meter in
measurement mode A counts every direction as imported, so it has no exported
energy. The **Measuring system** and **Measurement mode** sensors show what
the meter is set to.

**Enabled by default:**

- **Power**, and **Power L1** to **L3**. Negative power means export.
- **Current L1** to **L3**, and **Voltage L1** to **L3** against the neutral.
- **Power factor** and **Frequency**.
- **Energy imported** and **Energy exported**: the totals since the meter was
  installed. These are the sensors for the Energy dashboard.
- **Measuring system** and **Measurement mode** (diagnostic).
- **Wiring error** (diagnostic), see [good to know](#good-to-know).
- **Reset partial counters** (button).

**Disabled by default**, enable them on the device page:

- Voltages between phases; apparent and reactive power, in total and per
  phase; power factor per phase.
- Partial, per-phase, reactive and per-tariff energy counters.
- Demand values and their maximums, neutral current, voltage and current THD
  (EM530 and EM540), run hours.
- Phase sequence, active tariff and meter state.
- The meter's other settings: demand interval, what the digital input does
  (or what selects the tariff), and whether its wiring check is on.
- Alarm and digital input (EM530 and EM540).
- Reset demand and Reset tariff counters (EM530 and EM540).

The meter's settings are shown, but not changed: they belong to whoever
installed the meter, and changing how it counts energy by mistake would spoil
its history. The lifetime totals cannot be reset from Home Assistant either.

### Energy dashboard

Under **Settings → Dashboards → Energy → Electricity grid**, pick the meter's
**Energy imported** for grid consumption and **Energy exported** for return
to grid, and its **Power** sensor for the power.

If **Energy exported** is missing, the meter is in measurement mode A, which
adds what you send back to what you take.

## Update interval

The readings are polled every 2 seconds by default. Set the **Update
interval** while adding the meter, or later in the integration's
**Configure** dialog, from 0.01 to 300 seconds. Use 1 second or less for
something like battery control. This option is specific to this custom
integration: Home Assistant core does not let integrations make their polling
interval configurable.

Only what the enabled entities show is read: a block no enabled entity uses is
skipped. The **Configure** dialog shows how long the last poll took.

An interval shorter than a poll takes is allowed, but you are warned first,
with the poll time estimated for the baud rate (or, in **Configure**, the
last poll measured). Updates cannot come faster than a poll takes: Home
Assistant starts the interval when a poll ends, so the meter is then read
without pause, other devices on the same bus wait longer for their turn, and
every update writes new states to the database. Behind an RS485-to-TCP gateway
the baud rate is not known at setup, so the check waits for **Configure**.

Measured on an EM540 (firmware 1.4.3) behind a wired ESPHome serial proxy:

| Baud rate | Poll with every entity enabled |
| --- | --- |
| 9600 | about 1.05 s |
| 38400 | about 0.56 s |
| 57600 | about 0.51 s |
| 115200 | about 0.45 s |

With the default entities, a poll at 57600 baud takes about 0.16 s.

The meter refreshes its values every 80 ms. At 9600 baud a poll of every
entity takes longer than a second, so for a 1-second interval set the meter to
38400 baud or faster, or keep the extra entities disabled.

The meter's settings are read every 10 minutes. When one changes in a way that
adds or removes entities, such as the measurement mode, the integration
reloads by itself.

## Good to know

- **Wiring error** is the meter's own wrong-connection flag, and is only
  reported while the meter's wiring check is on. It also turns on when one
  phase exports while the others import, such as with a single-phase solar
  inverter or battery. If that is your installation, the flag is not a wiring
  problem.
- If part of the meter does not answer a poll, it is asked once more straight
  away. If it still does not answer, only its entities become unavailable.
- After the meter has stopped answering, its serial number is read again
  before new readings are taken. If a different meter answers at the address,
  for example after a replacement, its entities stay unavailable and the log
  says so. Set the new meter up as a new entry.
- Several meters on one bus, each with its own address, can each be set up as
  their own entry. They share one connection and take turns on the bus.
- **Download diagnostics** on the device page reads every register the meter
  serves, decoded and raw, with the serial number left out. Attach it to an
  issue.

## Troubleshooting

- **Setup cannot connect:** check the baud rate and address against the
  meter's setup menu, try swapping the A and B wires, and make sure nothing
  else polls the bus. For a gateway, check that it is in transparent mode at
  the meter's baud rate, 8N1.
- **Setup reports an unsupported model code:** something else answers on that
  address, or the meter is of another series. Check the address, and the model
  on the meter's front.

## Develop

The integration is developed for Home Assistant core, and this repository is
exported from that work with `tools/export_from_core.py`; `SOURCE` names the
core commit. The tests run against Home Assistant 2026.10.2 and need Linux (or
WSL):

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
