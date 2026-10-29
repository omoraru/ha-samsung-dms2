# Samsung DMS (legacy firmware) — Home Assistant integration

Local control of a **Samsung DVM air-conditioning system** managed by an older
**DMS2 / DMS2.5 "Data Management Server"** (the `MIM-B18` / `MIM-D01`-class
central controllers) that still ships the **2017 Silverlight web UI**.

Those panels drive a single XML-over-POST endpoint (`/dms2/dataCommunication`)
behind a Microsoft Silverlight front-end. Silverlight is dead, and the modern
[`samsung_dms`](https://github.com/albertovincenzi/ha_samsung_dms) integrations
target newer firmware whose REST-ish endpoints return **404** on these old
units. This integration speaks the old panel's own protocol directly — **no
cloud, no Silverlight, no account** — over the local network.

> ⚠️ **Community project, not affiliated with Samsung.** Use at your own risk.
> It talks to live building HVAC equipment. **Control is OFF by default**;
> read the safety notes before enabling it.

## Features

- Auto-discovers every indoor unit and exposes each as a `climate` entity,
  named from the labels configured on the DMS.
- **Read:** power/HVAC mode (cool/heat/dry/fan/auto), target & room temperature,
  fan speed, plus per-unit `fault`, `filter_warning`, `remote_control_enabled`,
  `scheduled` and `defrost` attributes.
- **Control (opt-in):** power on/off, HVAC mode, target temperature (within the
  unit's own limits), fan speed — sent as the panel's native `setDeviceControl`.
- **Per-unit protection:** addresses you list stay read-only even when control
  is enabled (e.g. units that must never be switched).
- **Fault & filter binary sensors** (`problem` class) per unit, so faults and
  filter-cleaning warnings can drive Home Assistant notifications directly. The
  fault sensor carries the panel's error **code and description** (e.g.
  `387 — Outdoor fan 2 Hall Sensor Error`), pulled from `getStatusUpload`.
- **Off units report room temperature as unknown**, not the misleading stagnant
  reading an idle indoor unit's return-air thermistor gives with no airflow (the
  raw value stays in the `raw_room_temp` attribute).
- Units behind a faulted outdoor unit (which the panel reports as `null`) show
  up as `unavailable` rather than as bogus state.
- Pure local polling; re-logs in automatically on session expiry.

## Supported hardware

Confirmed on a `MIM-B18` DMS2.5 running the 2017 Silverlight firmware (web UI
titles itself `DMS2`, `/dms2/` served). It should work on any DMS2/DMS2.5 panel
that serves the Silverlight UI at `https://<panel>/dms2/Login.jsp` and answers
on `/dms2/dataCommunication`. Newer firmware with the HTML UI (DMS 2.5
v2.9.0.15+) exposes different endpoints — use the mainline `samsung_dms`
integration there instead. See [`PROTOCOL.md`](PROTOCOL.md) for the wire format.

## Installation

### HACS (custom repository)

1. HACS → Integrations → ⋮ → **Custom repositories**.
2. Add `https://github.com/omoraru/ha-samsung-dms2`, category **Integration**.
3. Install **Samsung DMS (legacy firmware)**, then restart Home Assistant.

### Manual

Copy `custom_components/samsung_dms_legacy/` into your HA
`config/custom_components/` directory and restart.

## Configuration

Settings → Devices & Services → **Add Integration** → *Samsung DMS (legacy firmware)*.

| Field    | Notes                                              |
|----------|----------------------------------------------------|
| Host     | The DMS IP, e.g. `192.168.0.100`                   |
| Username | Usually `admin`                                    |
| Password | Your DMS password (often printed on the panel lid) |
| Polling  | Seconds between refreshes (default 30)             |

The panel ships a self-signed certificate; the integration does not verify it.

### Enabling control

Control is **disabled by default** so you can verify the entity↔room mapping
first. Then: Settings → Devices & Services → **Samsung DMS (legacy firmware)** →
**Configure**:

- **Enable control** — turns on on/off, mode, setpoint and fan.
- **Protected addresses** — comma-separated unit addresses (e.g.
  `11.00.05,11.00.06`) that must *never* be controlled. They stay read-only and
  refuse every command even with control enabled.

Commands on a protected or control-disabled unit surface a clear message in the
UI instead of failing silently. Toggling control reloads the integration.

## How it works

The 2017 firmware authenticates via a "secured form" POST (the credentials are
concatenated with the `JSESSIONID` and posted as `securedUsername` /
`securedPassword`), then drives everything through `POST /dms2/dataCommunication`
with an XML body of the form `"<uuid>:<xml>"`. Full details, including the
`setDeviceControl` write format, are in [`PROTOCOL.md`](PROTOCOL.md).

## Limitations

- Reading/writing the DMS's built-in schedules is not implemented (use HA
  automations instead).
- Energy/power metering is not implemented.
- EHS/hydro and ERV units are not yet mapped to dedicated entities (only indoor
  AC units become `climate` entities). PRs welcome.

## Credits

Protocol reverse-engineered from the panel's own shipped `Login.xap` /
`DMS_Client.dll` and `dms2global.js`, and confirmed against live hardware.
Inspired by the newer-firmware
[`ha_samsung_dms`](https://github.com/albertovincenzi/ha_samsung_dms) project.

## License

[MIT](LICENSE).
