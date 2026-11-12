# Tuya Cloud Devices for Home Assistant

A Home Assistant custom integration using Tuya's new **2C end-user Cloud API** — no developer IoT platform account needed. Just your API key from the Tuya Smart app.

## What's Different

The official Tuya integration requires creating a developer project on iot.tuya.com, linking your Tuya app account, and managing OAuth credentials. This integration uses Tuya's simplified 2C API released November 2026, which only needs a single API key.

| Feature | Official Tuya | Tuya Cloud Devices |
|---|---|---|
| Auth | OAuth + developer project | Single API key |
| Setup | Multi-step developer portal | Paste key in HA |
| Real-time | Polling only | WebSocket push + polling fallback |
| Device model | Hardcoded mappings | Dynamic Thing Model |

## Supported Platforms

- **Lights** — on/off, brightness, color temperature
- **Switches** — single and multi-gang, power monitoring outlets
- **Climate** — AC units, thermostats (mode, temperature, fan speed)
- **Sensors** — temperature, humidity, power, voltage, current, energy, PM2.5, CO2, VOC, battery
- **Covers** — curtains, blinds (open/close/stop, position)

Device capabilities are discovered dynamically from the Tuya Thing Model, so new device types get basic support automatically.

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three-dot menu and select **Custom repositories**
3. Add the repository URL and select **Integration** as the category
4. Search for "Tuya Cloud Devices" and install
5. Restart Home Assistant

### Manual

Copy the `custom_components/tuya_cloud` folder into your Home Assistant `config/custom_components/` directory and restart.

## Configuration

1. Go to **Settings > Devices & Services > Add Integration**
2. Search for **Tuya Cloud Devices**
3. Enter your API key (starts with `sk-`)
4. The integration auto-detects your data center from the key prefix

### Getting Your API Key

1. Open the **Tuya Smart** app (or **Smart Life**)
2. Go to **Settings > Developer Options**
3. Copy your API key

The key prefix determines your data center:
- `AZ` — US West
- `UE` — US East
- `AY` — China
- `EU` — Europe
- `IN` — India

## How It Works

- **Polling**: Every 2 minutes as a fallback
- **WebSocket**: Real-time device state push for instant updates
- **Thing Model**: Device capabilities are fetched from Tuya's cloud, so the integration adapts to each device's actual features rather than relying on hardcoded mappings

## Troubleshooting

**"Authentication failed"** — Double-check your API key. It must start with `sk-`.

**Devices not appearing** — The integration loads devices from your Tuya home. Make sure devices are assigned to a home in the Tuya Smart app.

**Slow updates** — If WebSocket disconnects, the integration falls back to 2-minute polling and auto-reconnects. Check your HA logs for connection errors.

## Credits

Built on Tuya's open-source [OpenClaw Skills](https://github.com/tuya/tuya-openclaw-skills) reference implementation.
