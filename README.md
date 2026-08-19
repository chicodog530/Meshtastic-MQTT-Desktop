# Meshtastic MQTT Desktop

A cross-platform Python/Tkinter desktop client for receiving, decoding, organizing, and sending Meshtastic traffic through an MQTT broker without requiring a local LoRa radio.

The included profile targets the public LZMesh service in southwest Missouri. Broker, topic, gateway, channel, and key settings are editable for use with other compatible Meshtastic MQTT networks.

> **Project status:** Experimental. Receiving and decoding are mature enough for routine testing. MQTT-to-RF transmission depends on the selected gateway, its channel configuration, downlink policy, and RF reach.

## Features

- Native Windows and Linux GUI using Python's built-in Tkinter toolkit
- Dark Mode support via `sv_ttk`
- Configurable MQTT host, port, credentials, TLS, topic root, gateway, and channel keys
- Receives Meshtastic JSON and encrypted protobuf traffic
- Decodes text, node information, positions, telemetry, traceroutes, routing acknowledgements, and other supported packet types
- Messages, Nodes, Positions, Map, and Diagnostics tabs
- Interactive Map tab (`tkintermapview`) to visualize node positions
- Persistent contact list with long name, short name, hardware, channel, gateway, hops, last-heard time, and coordinates
- Displays recognizable node names throughout the interface when known
- Right-click message actions for selecting a sender, opening its contact, or requesting node information
- Blue highlighting for unnamed nodes whose information can be requested (0–1 hop)
- Gray highlighting for unnamed nodes beyond the gateway's one-hop request reach
- Direct encrypted text messages and selected-channel broadcasts
- Virtual Meshtastic identity for MQTT-originated packets
- Optional position broadcast with confirmation
- Reverse-geocoding and OpenStreetMap actions for received positions
- Raw packet viewer and persistent diagnostic log
- Private PKI packets identified without misleading decode errors
- About dialog with version and repository link

## Requirements

- Windows 10/11 or a current Linux distribution
- Python 3.10 or newer (3.11 or 3.12 recommended)
- Internet access to the configured MQTT broker
- Tkinter (included with standard Windows Python; Linux may require a separate package)
- A broker account and compatible Meshtastic channel information

Python packages are listed in `requirements.txt`: `paho-mqtt`, `meshtastic`, and `cryptography`.

## Installation

### Windows 10/11

1. Install Python from [python.org](https://www.python.org/downloads/). Enable **Add Python to PATH**.
2. Download this repository with **Code → Download ZIP**, then extract it.
3. Open PowerShell in the extracted folder.
4. Run:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
py main.py
```

On later launches, activate the environment and run the final command, or double-click `start_windows.bat`.

If PowerShell blocks activation, use Command Prompt:

```bat
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

### Ubuntu/Debian

```bash
sudo apt update
sudo apt install python3 python3-venv python3-tk
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

For other Linux distributions, install Python 3, Tkinter, and virtual-environment support with the system package manager.

## First launch

1. Open **Settings**.
2. Review the broker profile and credentials.
3. Keep **Enable experimental sending** off initially.
4. Save, then press **Connect**.
5. Confirm that Diagnostics reports a successful connection and subscriptions.
6. Watch the Messages, Nodes, and Positions tabs populate.

Local data is saved under `%USERPROFILE%\.meshtastic_mqtt_desktop` on Windows or `~/.meshtastic_mqtt_desktop` on Linux. It includes `config.json`, `contacts.json`, and `events.log`; all are excluded from Git.

## Using the interface

### Messages

Messages shows the time, direction, sender, packet type, channel, decoded content, hop count, and gateway. Double-click a row or use **View raw packet** to inspect its MQTT topic and payload.

Right-click a message to request the sender's node information when it is within 0–1 hop, use the sender as the message destination, or jump to its saved contact. Unnamed requestable nodes appear blue; unnamed nodes beyond one hop appear gray.

### Nodes and contacts

Node records are saved automatically. NODEINFO packets supply long name, short name, and hardware model. Select a row to use it as a destination, edit or delete it, or request node information.

The LZMesh bridge generally cannot deliver node-information requests or direct messages beyond one RF hop. The app disables those actions and removes known distant nodes from the destination dropdown. Use **Edit contact** to add a recognizable manual name when needed.

### Positions

Right-click a position to look up its approximate town/county/state, open it in OpenStreetMap, or copy its coordinates. Reverse-geocoding occurs only when requested and uses OpenStreetMap Nominatim. Results are cached in the contact record.

### Diagnostics

Diagnostics shows connection events, subscriptions, publish results, decode notices, and the persistent log path. Remove credentials and private locations before sharing diagnostic output.

## Sending messages

Sending is disabled by default.

1. Confirm the selected gateway supports MQTT downlink and the selected channel.
2. Enable **experimental sending** in Settings.
3. Select a gateway and channel.
4. Select a known node for a direct message, or **Broadcast (selected channel)** for a channel-wide message.
5. Enter a short plain-text message and press **Send**.

Direct messages request a routing acknowledgement. Broadcasts use destination `0xFFFFFFFF`. MQTT accepting a publication does not guarantee RF delivery or reception.

The LZMesh gateway is reported to retransmit MQTT traffic over RF for approximately one hop. A distant node visible through MQTT may therefore be unreachable from the selected bridge over RF.

## Sending a location

Press **Send location…**, enter latitude, longitude, and optional altitude, then review the confirmation. Location packets are channel broadcasts from the application's virtual identity. Do not publish a private location unless you intentionally want it visible to other users and mapping services.

## Configuration reference

| Setting | Purpose |
|---|---|
| Profile | Friendly name for the current configuration |
| Broker host/port | MQTT server endpoint |
| Username/password | Broker authentication |
| Topic root | Network topic prefix, such as `msh/LZ` |
| Preferred gateway | Gateway used before live gateways are learned |
| Channel name/index | Meshtastic channel used by the profile |
| Channel PSKs | Base64 channel keys used to decode/send packets |
| TLS | Enables encrypted MQTT transport when supported |
| Experimental sending | Allows text, node-info requests, and positions |

The bundled LZMesh connection data and keys were published in the network's public setup tutorial. For other networks, obtain settings from the administrator. Never publish private credentials or private channel keys.

## Troubleshooting

### Connected but no packets appear

- Verify the topic root and credentials.
- Leave the app connected long enough for periodic traffic.
- Check Diagnostics for the exact subscriptions.
- Confirm the broker ACL permits those topics.

### Meshtastic package is installed but protobuf support is missing

The package is probably in another Python environment. Launch using the virtual environment:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

### PKI/private packet cannot be decrypted

PKI traffic uses recipient-specific encryption and is not expected to decode with ordinary channel keys. The app labels it as private.

### Message publishes but no radio receives it

Check that the gateway is online, downlink-enabled, on the same channel, within RF range, and permitted to retransmit MQTT traffic.

### Node-info request does not return a name

The node may be asleep, on another channel, out of RF range, or more than one hop away. Names may arrive later through routine NODEINFO broadcasts. Use **Edit contact** as a fallback.

### Tkinter is missing on Linux

```bash
sudo apt install python3-tk
```

See [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) for more detail.

## Data and security

- Broker passwords are stored as plain text in the per-user configuration file.
- Contacts can include precise coordinates and place names.
- Logs may contain node IDs, messages, topics, and network activity.
- `.gitignore` excludes local data, caches, environments, and build products.
- Review [`SECURITY.md`](SECURITY.md) before publishing a modified configuration.

## Testing

```bash
python -m unittest discover -v
python -m py_compile main.py mqtt_logic.py protobuf_codec.py protobuf_sender.py
```

Live broker/RF behavior must also be tested manually because it depends on external infrastructure.

## Project files

| File | Purpose |
|---|---|
| `main.py` | GUI, MQTT lifecycle, contacts, and user actions |
| `mqtt_logic.py` | Topic and JSON parsing helpers |
| `protobuf_codec.py` | Incoming protobuf decryption and decoding |
| `protobuf_sender.py` | Outgoing encrypted packet construction |
| `test_*.py` | Offline unit tests |
| `requirements.txt` | Runtime dependencies |
| `ANTIGRAVITY_BUILD_PLAN.md` | Detailed continuation plan |

## Contributing and license

Bug reports and pull requests are welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md). Licensed under the [MIT License](LICENSE).

Current release: **v0.18**. See [`CHANGELOG.md`](CHANGELOG.md).
