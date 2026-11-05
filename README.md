# Dreame Dehumidifier for Home Assistant

A custom integration for Dreame dehumidifiers that are set up in the
**Dreamehome** app. It talks to Dreame's cloud, the same way the app does.

Not affiliated with Dreame.

## Supported models

| Model | ID | Status |
|---|---|---|
| DD20 | `dreame.dehum.u2512` | Reads and writes confirmed on a real unit |

Other Dreame dehumidifiers can be added from the account, but they get no
entities until they have a profile: sending one model's commands to another can
upset some Dreame devices, so the integration doesn't guess. See
[Adding a model](#adding-a-model).

## What you get (DD20)

| Entity | Type | Property |
|---|---|---|
| Dehumidifier: on/off, mode (Auto, Sleep, Dry, Custom), target humidity 30–80 % | `humidifier` | 2/1, 2/3, 2/5 |
| Fan speed (Low, High; switches to Custom first) | `select` | 2/4 |
| Humidity, temperature | `sensor` | 3/2, 3/3 |
| Child lock, plasma, swing, key tone, auto air drying on power-off | `switch` | 5/1, 7/6, 7/7, 4/1, 2/6 |
| Air drying: start or stop the 40 minute self-drying cycle (starts only while the unit is on) | `switch` | 2/10 |
| Water tank alert (on when the tank is out) | `binary_sensor` | 2/2 |
| Air drying time remaining and duration | `sensor` | 2/7, 7/8 |
| Timer in hours (1-12, 0 cancels) and whether it is active | `number`, `binary_sensor` | 7/2, 7/1 |
| Properties not understood yet, as raw values (disabled by default) | `sensor` | 6/4, 7/5 |

Known gaps on the DD20:

- The tank alert was confirmed by taking the tank out; a full tank wasn't tested.
- No drying/idle state: the unit doesn't report whether its compressor runs.
- Property 7/3 holds the place name set in the app. It is never read.

## Installation

### HACS

1. HACS → ⋮ → **Custom repositories** → add this repository's URL as an
   **Integration**.
2. Install **Dreame Dehumidifier** and restart Home Assistant.

### Manual

Copy `custom_components/dreame_dehum` into your Home Assistant
`config/custom_components` folder and restart.

## Setup

**Settings → Devices & services → Add integration → Dreame Dehumidifier**, then
sign in with your Dreamehome email and password and pick the region your
account was created in.

If you sign in to the app with Google or Apple, add a password to the account
first: in the Dreamehome app, **Profile → Settings → Account and Security**.

Options: the update interval (default 30 s).

## Privacy

The integration stores your Dreamehome email and password in Home Assistant's
config entry, like other cloud integrations; the password is sent to Dreame
only as the salted hash the app uses. Diagnostics downloads remove the
account, device ID, MAC, cloud host and serial number.

## Adding a model

`tools/probe.py` maps a dehumidifier from a computer, with the standard library
only:

```bash
python3 tools/probe.py list
python3 tools/probe.py sweep --did <device id>   # which properties exist (reads only)
python3 tools/probe.py learn --did <device id>   # what each one means (reads only)
```

`learn` walks you through changing one setting at a time in the Dreamehome app
and records which properties changed. Both reports leave out account and
device identifiers and replace text values with their length; check them
before attaching them to an issue. Then add a `Profile` in
`custom_components/dreame_dehum/profiles.py`.

`python3 tools/probe.py write --did <id> 2/5 55` writes one property and reads
it back, to confirm a write works. It asks before writing.

## Credits

The Dreame cloud client and the structure of this integration are adapted from
[ha-dreame-air](https://github.com/MrJiggs0003/ha-dreame-air) (MIT), which
builds on [ha-dreame-fp10](https://github.com/yarimati/ha-dreame-fp10) (MIT).
See `NOTICE`.

## License

MIT
