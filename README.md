# HA Ember+ – Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A [Home Assistant](https://www.home-assistant.io/) custom integration for devices using the **Ember+** protocol.  
Auto-discovers all parameters and exposes them as switches, numbers, and sensors.

---

## Features

| Value type | Platform | Description |
|---|---|---|
| **Boolean** | `switch` | Toggle switches (GPI, GPO, PFL, Channel ON, Faderstart, Active, …) |
| **Integer** | `number` | Numeric controls (Fader level, …) |
| **String** | `sensor` | Text values (Channel label, …) |

- Connects to the device over **TCP port 9000** (configurable)
- **Auto-discovery** of the full Ember+ parameter tree
- **Instant push updates** – state changes are received in real-time
- Automatic **reconnection** on connection loss
- Full **config flow UI** – no YAML needed
- **HACS** compatible

## Requirements

- A device with Ember+ support (e.g. audio mixing consoles)
- Ember+ enabled in the device configuration
- Network connectivity between Home Assistant and the device

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations** → **⋮** → **Custom repositories**
3. Add `https://github.com/jessygoldfinger/HA-EmberPlus` and select **Integration** as the category
4. Search for **HA Ember+** and install it
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/ember_plus` folder into your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **HA Ember+**
3. Enter the **IP address** and **port** (default: 9000) of your Ember+ device
4. The integration will **auto-discover** all parameters from the Ember+ tree
5. Select which parameters you want to add (grouped by node, e.g. "MIC > Fader")
6. You can add or remove parameters later via **Options** on the integration card

## Protocol Reference

This integration uses the **Ember+** protocol over TCP.

- **Port:** 9000 (default)
- **Framing:** S101 (byte-stuffed with CRC-CCITT16)
- **Encoding:** BER (ASN.1) with Glow DTD
- **Tree structure:** auto-discovered via recursive `getDirectory` walk

Full protocol documentation: [github.com/Lawo/ember-plus](https://github.com/Lawo/ember-plus/wiki)

## Troubleshooting

- **Cannot connect:** Verify the device IP is reachable from your HA host (`ping <ip>`). Ensure TCP port 9000 is not blocked by a firewall. Check that Ember+ is enabled on the device.
- **No parameters found:** Verify that the device exposes parameters via Ember+.
- **Entity unavailable:** The device may have closed the socket. The integration will automatically reconnect.

## Contributing

Contributions are welcome! Please open an issue or pull request on GitHub.

## License

[MIT](LICENSE)
