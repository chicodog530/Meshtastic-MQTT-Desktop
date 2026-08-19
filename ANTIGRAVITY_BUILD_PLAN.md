# Meshtastic MQTT Desktop — Detailed Build Plan

## 1. Project goal

Build a cross-platform Python desktop GUI that lets a user participate in a Meshtastic network through its MQTT infrastructure without owning or connecting an RF/LoRa device.

The first target is LZMesh/Joplin, Missouri, but nothing in the program should be hard-coded to one network. The user must be able to create and edit broker profiles for other Meshtastic MQTT networks.

The application should:

- Run on Windows 11 and Ubuntu.
- Connect directly to a configurable MQTT broker.
- Display live Meshtastic messages and useful node/gateway activity.
- Send channel messages through a compatible MQTT gateway.
- Eventually support direct messages, node lists, telemetry, positions, and a map.
- Require no local Meshtastic radio.
- Use a conventional desktop GUI; do not make the primary application a terminal program.

Working name: **Meshtastic MQTT Desktop**.

## 2. Initial LZMesh defaults

Use these only as the bundled default profile. Every value must remain editable.

| Setting | Default |
| --- | --- |
| Profile name | LZMesh (Joplin) |
| Broker | `mqtt.lzmesh.com` |
| Port | `1883` |
| Username | `meshdev` |
| Password | `large4cats` |
| TLS | Off |
| Root topic | `msh/LZ` |
| Channel name | `LZMesh` |
| Channel index | `1` |
| Channel PSK | `uLT6S8kQlQHjA7yEtBkzIj3zm6K6lE55mulplDZyF/0=` |
| JSON traffic | Enabled on documented LZMesh setup |
| Meshtastic encryption | Enabled on documented LZMesh setup |

The program should never expose a saved password or PSK in normal logs.

## 3. Important protocol constraint

An MQTT broker is not itself a virtual Meshtastic radio. A message published by the app reaches RF only if an internet-connected Meshtastic gateway is subscribed to the relevant downlink topic and is configured to retransmit it.

There are two possible send paths:

### Path A — JSON downlink (first working implementation)

Publish a JSON command to a gateway-specific topic:

`<root>/2/json/<channel-name>/<gateway-id>`

Example topic:

`msh/LZ/2/json/LZMesh/!7efeee00`

Example payload:

```json
{"from":2130636288,"channel":1,"type":"sendtext","payload":"Hello from the desktop app"}
```

For a direct message, add decimal `to`:

```json
{"from":2130636288,"to":305441741,"channel":1,"type":"sendtext","payload":"Private test"}
```

The `from` number must be the decimal form of the selected gateway's hexadecimal node ID. The gateway must have MQTT consume/downlink and JSON command handling enabled.

### Path B — encrypted protobuf (compatibility phase)

New Meshtastic firmware has deprecated or removed native JSON MQTT processing in some builds. For those networks, implement an encrypted protobuf `ServiceEnvelope` path or integrate the official-style MQTT protobuf-to-JSON converter architecture.

Do not assume that publishing an arbitrary `ServiceEnvelope` to a topic will cause RF transmission. Firmware loop protection and gateway-specific subscriptions must be tested. The GUI should expose the supported send mechanism per broker profile:

- Auto-detect
- JSON downlink
- Protobuf/converter
- Receive-only

If no verified injection path exists, clearly show **Receive only** rather than reporting a false send success.

## 4. GUI requirements

Use Python with `tkinter`/`ttk` for the first version because it is included with normal Windows and Ubuntu Python distributions. Keep network work off the GUI thread.

### Main window

Top status bar:

- Active profile name
- Connection state: Disconnected / Connecting / Connected / Error
- Broker hostname
- Connect and Disconnect buttons
- Settings button

Main message table:

- Local receive time
- Network timestamp
- Sender node ID
- Sender long name, when known
- Message type
- Channel/index
- Message text or summarized payload
- Gateway ID
- Optional RSSI/SNR/hops when present

Message composer:

- Gateway selector
- Destination selector: Broadcast or known node
- Channel selector
- Text entry
- Character/byte count
- Send button
- Result state: Published, observed echo, gateway accepted, timed out, or failed

Secondary tabs planned:

1. **Messages** — channel chat and direct messages.
2. **Nodes** — node ID, long/short name, last heard, hardware, gateway source.
3. **Telemetry** — battery, voltage, channel utilization, environmental readings.
4. **Map** — interactive map showing positions reported over MQTT.
5. **Raw traffic** — optional diagnostic topic/payload viewer with export.
6. **Log** — connection events and non-secret diagnostics.

### Settings dialog

Broker profile fields:

- Profile name
- Host
- Port
- Username
- Password
- TLS on/off
- CA certificate path, optional
- Root topic
- Channel name
- Channel index
- Channel PSK, optional and masked
- Send mechanism
- Receive JSON topics on/off
- Receive encrypted protobuf topics on/off
- Reconnect automatically on/off
- Keepalive seconds

Profile management:

- New
- Duplicate
- Rename
- Delete with confirmation
- Save
- Test connection
- Import/export a profile with secrets excluded by default

## 5. MQTT topic strategy

Subscribe initially to:

- `<root>/2/json/#` for readable JSON traffic.
- Optionally `<root>/2/e/#` for encrypted protobuf traffic.
- Optionally `<root>/2/c/#` for compatibility with firmware older than 2.3.

Never subscribe to `#` across the entire broker unless the user deliberately enables a diagnostic mode.

Extract gateway IDs from:

- The final topic segment when it is a valid `!xxxxxxxx` node ID.
- The JSON `sender` property.
- The protobuf `gateway_id` property in a decoded `ServiceEnvelope`.

Keep a gateway table with last-seen time, topics observed, channels observed, and whether a successful downlink/echo has been confirmed.

## 6. Receive pipeline

MQTT callbacks must do very little work. They should put immutable events onto a thread-safe queue. The GUI thread drains the queue with `after()`.

Pipeline:

1. MQTT message received.
2. Classify topic as JSON, encrypted protobuf, legacy protobuf, or unknown.
3. Parse safely; malformed traffic must not crash the application.
4. Normalize unsigned 32-bit node numbers to `!xxxxxxxx` strings.
5. Update gateway inventory.
6. Update node inventory from node-info messages.
7. Deduplicate messages using message ID plus sender.
8. Store recent traffic in SQLite.
9. Emit a presentation model to the GUI.

Supported JSON message types in early releases:

- `text`
- `nodeinfo`
- `position`
- `telemetry`
- `waypoint`
- `neighborinfo`
- `traceroute`
- `detection_sensor`
- unknown types shown as summarized JSON

## 7. Sending workflow

1. Require an active broker connection.
2. Require a selected gateway unless the broker profile defines a tested gateway/topic.
3. Validate channel, destination, and UTF-8 payload size.
4. Construct the downlink using the profile's send mechanism.
5. Publish with QoS 0 unless the broker/network specifically requires otherwise.
6. Record a local pending-send entry with a generated correlation ID.
7. Watch incoming traffic for an echo or matching message.
8. Change status from Published to Observed if a matching message appears.
9. Time out cleanly if no echo is observed. Explain that MQTT publish success does not prove RF transmission.

Do not use retained MQTT messages for chat or downlink commands.

## 8. Data model and persistence

Store application settings under the current user's application-data directory, not alongside the executable.

Recommended:

- Windows: `%APPDATA%/MeshtasticMQTTDesktop/`
- Linux: `$XDG_CONFIG_HOME/meshtastic-mqtt-desktop/` or `~/.config/meshtastic-mqtt-desktop/`

Use JSON for profiles in the first version. Move message/node history to SQLite:

- `profiles`
- `messages`
- `nodes`
- `gateways`
- `send_attempts`

Store passwords using the operating-system keyring in a later security pass (`keyring` package). Until then, visibly warn that passwords are stored locally in plain text.

## 9. Suggested Python structure

```text
meshtastic_mqtt_app/
  main.py                    GUI entry point
  app/
    gui/
      main_window.py
      settings_dialog.py
      message_view.py
      nodes_view.py
    mqtt/
      client.py
      topics.py
      json_codec.py
      protobuf_codec.py
      crypto.py
    models/
      message.py
      node.py
      gateway.py
      profile.py
    storage/
      config.py
      database.py
    services/
      receive_service.py
      send_service.py
  tests/
  requirements.txt
  README.md
```

The current prototype keeps fewer files for speed. Refactor toward this structure when the functionality grows.

## 10. Dependencies

First version:

- Python 3.11 or newer
- `paho-mqtt` 2.x
- Standard-library `tkinter`, `json`, `queue`, `threading`, and `pathlib`

Protobuf phase:

- `meshtastic` Python package for generated protobuf definitions, or pin compatible `meshtastic-protobufs`
- `cryptography` for AES-CTR if encrypted payload decoding is implemented locally
- Never write custom protobuf wire encoding

Packaging phase:

- `PyInstaller` for a Windows `.exe` and Linux bundle
- Build separately on each operating system; do not cross-build the Windows executable on Linux

## 11. Security and safety

- Mask passwords and PSKs in the GUI.
- Do not print secrets in logs or error reports.
- TLS certificate validation must stay enabled when TLS is selected.
- Limit message length to Meshtastic's actual payload constraints.
- Never send retained downlinks.
- Provide a receive-only mode.
- Rate-limit sends to avoid flooding the RF mesh.
- Label the selected gateway and channel prominently before sending.
- Do not invent a user/node identity that could impersonate an existing RF node. JSON downlink uses the chosen gateway's required `from` value; explain this behavior in the UI.

## 12. Test plan

Unit tests:

- Root topic normalization.
- JSON subscription/downlink topic construction.
- Node ID hex/decimal conversion.
- JSON envelope creation for broadcast and DM.
- JSON parsing for every supported packet type.
- Malformed UTF-8 and malformed JSON.
- Signed/unsigned 32-bit IDs.
- Secret redaction.

Integration tests:

- Connect/disconnect/reconnect to a test Mosquitto broker.
- Credential rejection.
- TLS success and certificate failure.
- Subscribe and display fixture messages.
- Discover multiple gateway IDs.
- Publish JSON downlink and verify exact topic/payload.
- Simulate a message echo and send timeout.

Live LZMesh acceptance tests:

1. Connect and receive traffic without an RF device.
2. Confirm discovered Joplin/LZMesh gateway IDs.
3. Select one active compatible gateway.
4. Send a uniquely tagged low-volume test message with permission from the network operators.
5. Confirm it appears on broker traffic.
6. Confirm separately whether it reaches a Meshtastic client or RF node.
7. Record the exact gateway firmware and required topic shape.

## 13. Delivery phases

### Phase 1 — GUI MQTT monitor and JSON sender

- Desktop GUI.
- Editable LZMesh profile.
- Connect/disconnect.
- JSON subscription.
- Message table.
- Automatic gateway discovery.
- Broadcast and DM JSON publishing.
- Clear publish-versus-RF-delivery status.
- Receive-only default, explicit experimental-send opt-in, automatic reconnect, and persistent reason-code logging.

### Phase 2 — useful chat client

- Node name cache.
- Conversation/channel filtering.
- SQLite history.
- Deduplication.
- Send echo tracking.
- Gateway health/last-seen display.
- Auto reconnect.
- v0.6 adds tabbed node/position/diagnostic views, node-name cache, RF columns, readable positions, traceroutes, and gateway deduplication.

### Phase 3 — protobuf compatibility

- Decode `ServiceEnvelope` protobuf packets.
- Decrypt channel payloads with configured PSKs.
- Add converter-compatible downlink support.
- Test against current Meshtastic firmware and LZMesh gateways.
- Keep JSON as a compatibility option.
- v0.4 implements encrypted `ServiceEnvelope` receive/decrypt for text, node info, position, and telemetry while retaining JSON fallback.
- v0.7 builds encrypted `TEXT_MESSAGE_APP` packets for direct-node and selected-channel broadcast delivery through a chosen MQTT gateway.

### Phase 4 — telemetry and mapping

- Nodes tab.
- Telemetry tab and charts.
- Position map.
- Export messages/nodes to CSV or JSON.

### Phase 5 — packaging

- Windows one-folder and optional one-file executable.
- Ubuntu installer/archive.
- Versioned config migration.
- In-app About/version panel.
- User documentation and troubleshooting guide.

## 14. Definition of done for first release

The first release is complete when a nontechnical Windows 11 user can unzip/install the app, open a GUI, select the bundled LZMesh profile, connect, see readable live traffic, see available MQTT gateways, type a message, select broadcast or a known destination, publish it through a compatible gateway, and receive an honest confirmation that distinguishes broker acceptance from observed network delivery.
