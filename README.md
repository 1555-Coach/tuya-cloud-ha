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

- **Lights** — on/off, brightness, color temperature, HS/RGB/RGBW color, work mode switching
- **Switches** — single and multi-gang, power monitoring outlets
- **Climate** — AC units, thermostats (mode, temperature, fan speed)
- **Cameras** — IPC/smart cameras with cloud snapshot capture
- **Fans** — speed (percentage and preset), oscillation, direction
- **Covers** — curtains, blinds (open/close/stop, position)
- **Locks** — lock/unlock, battery, unlock method tracking
- **Vacuums** — start/stop/pause, return to dock, fan speed, battery
- **Humidifiers** — humidifiers and dehumidifiers, target humidity, modes
- **Sirens** — alarm on/off, volume, duration, tone selection
- **Sensors** — temperature, humidity, power, voltage, current, energy, PM2.5, CO2, VOC, battery
- **Binary Sensors** — door/window contacts, motion, smoke, gas, water leak
- **Numbers** — any writable numeric property (auto-discovered)
- **Selects** — any writable enum property (auto-discovered)
- **Buttons** — write-only action triggers (auto-discovered)

Device capabilities are discovered dynamically from the Tuya Thing Model, so even unlisted device types get basic controls automatically via the generic number/select/button platforms.

## Installation

### HA Community Store (Recommended)

1. Go to **Settings > Add-ons & Store** in Home Assistant
2. Open the **Community Store** tab
3. Search for **Tuya Cloud Devices** or add it as a custom repository using the repo URL
4. Install and restart Home Assistant

### Manual

Copy the `custom_components/tuya_cloud` folder into your Home Assistant `config/custom_components/` directory and restart.

## Configuration

1. Go to **Settings > Devices & Services > Add Integration**
2. Search for **Tuya Cloud Devices**
3. Enter your API key (starts with `sk-`)
4. The integration auto-detects your data center from the key prefix

### Getting Your API Key

1. Go to **[tuya.ai](https://tuya.ai/)** (or [tuyasmart.com](https://tuyasmart.com/) for China)
2. Sign in with the same account you use in the **Tuya Smart** or **Smart Life** app
3. Generate and copy your API key

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

## Services

The integration registers these services for advanced use in automations and scripts:

### `tuya_cloud.send_notification`

Send a notification to the Tuya account owner via SMS, voice call, email, or app push.

```yaml
service: tuya_cloud.send_notification
data:
  method: push  # push, sms, voice, or email
  title: "Security Alert"
  message: "Motion detected in the living room"
```

### `tuya_cloud.get_statistics_config`

Query which devices support hourly energy/data statistics (returns response data).

### `tuya_cloud.get_statistics_data`

Query hourly statistics for a device (max 24-hour window, returns response data).

```yaml
service: tuya_cloud.get_statistics_data
data:
  device_id: "0620068884f3eb414579"
  dp_code: "ele_usage"
  statistic_type: "SUM"
  start_time: "2026111210"
  end_time: "2026111223"
```

## Troubleshooting

**"Authentication failed"** — Double-check your API key. It must start with `sk-`.

**Devices not appearing** — The integration loads devices from your Tuya home. Make sure devices are assigned to a home in the Tuya Smart app.

**Slow updates** — If WebSocket disconnects, the integration falls back to 2-minute polling and auto-reconnects. Check your HA logs for connection errors.

## Credits

Built on Tuya's open-source [OpenClaw Skills](https://github.com/tuya/tuya-openclaw-skills) reference implementation.
