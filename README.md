# HA DHD Ember+ – Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A [Home Assistant](https://www.home-assistant.io/) custom integration for **DHD audio mixing consoles** using the **Ember+** protocol.  
Control and monitor **GPI** (General Purpose Inputs) and **GPO** (General Purpose Outputs) over TCP.

---

## Features

| Capability | Platform | Description |
|---|---|---|
| **GPI** (read/write) | `switch` | Control a GPI as a toggle switch |
| **GPO** (read-only) | `binary_sensor` | Monitor a GPO as a binary sensor |

- Connects to the mixer over **TCP port 9000** (configurable)
- **Auto-discovery** of available GPIs and GPOs during setup
- **Instant push updates** – state changes are received in real-time
- Automatic **reconnection** on connection loss
- Supports up to **50 GPIs** and **50 GPOs** per mixer
- Full **config flow UI** – no YAML needed
- **HACS** compatible

## Requirements

- A DHD mixing console with Ember+ support:
  - **RM5200** series (XS, XC, XD, XS2, XC2, XD2) with firmware ≥ 8.x
  - **Series 52** cores (XS3, XC3, XD3) with firmware ≥ 10.x
- Ember+ enabled in the DHD device configuration
- Network connectivity between Home Assistant and the mixer

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations** → **⋮** → **Custom repositories**
3. Add this repository URL and select **Integration** as the category
4. Search for **HA DHD Ember+** and install it
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/dhd_ember` folder into your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **HA DHD Ember+**
3. Enter the **IP address** and **port** (default: 9000) of your DHD mixer
4. The integration will **auto-discover** all available GPIs and GPOs
5. Select which GPIs and GPOs you want to add
6. You can add or remove GPIs/GPOs later via **Options** on the integration card

## GPI vs GPO

| Type | Direction | HA Platform | Description |
|---|---|---|---|
| **GPI** | Input (read/write) | `switch` | Boolean inputs you can set from HA to trigger internal logics |
| **GPO** | Output (read-only) | `binary_sensor` | Boolean outputs driven by internal logics of the mixer |

- **GPIs** are configured in the DHD Toolbox project and can be used to trigger internal logics, switches, etc.
- **GPOs** are set by internal logic states and are read-only. The trigger logics must be configured in the DHD Toolbox project.

## Enabling Ember+ on your DHD mixer

Ember+ must be enabled in your DHD device configuration. Refer to the [DHD Ember+ documentation](https://support.dhd.audio/doku.php?id=tb9:emberplus) for setup instructions.

The Ember+ interface is available on TCP port **9000** by default.

## Protocol Reference

This integration uses the **Ember+** protocol over TCP.

- **Port:** 9000 (default)
- **Framing:** S101 (byte-stuffed with CRC-CCITT16)
- **Encoding:** BER (ASN.1) with Glow DTD
- **Tree structure:** `Device > GPI > GPI 1..50` and `Device > GPO > GPO 1..50`

Full protocol documentation: [github.com/Lawo/ember-plus](https://github.com/Lawo/ember-plus/wiki)  
DHD Ember+ documentation: [developer.dhd.audio](https://developer.dhd.audio/docs/api/ember/)

## Troubleshooting

- **Cannot connect:** Verify the mixer IP is reachable from your HA host (`ping <ip>`). Ensure TCP port 9000 is not blocked by a firewall. Check that Ember+ is enabled in the DHD configuration.
- **No GPIs/GPOs found:** Verify that GPIs and GPOs are configured in your DHD Toolbox project.
- **Entity unavailable:** The mixer may have closed the socket. The integration will automatically reconnect.

## Contributing

Contributions are welcome! Please open an issue or pull request on GitHub.

## License

[MIT](LICENSE)
