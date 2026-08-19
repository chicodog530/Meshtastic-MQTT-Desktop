# Changelog

## v0.18 — 2026-08-18

- Added an interactive Map tab using `tkintermapview` to display node locations.
- Added an About dialog with version and repository links.
- Added a dark mode option (enabled by default) using the `sv_ttk` theme.
## v0.17 — 2026-08-19

- Removed contacts beyond one hop from the direct-message destination dropdown.
- Disabled message-row and Nodes-tab destination actions for known nodes beyond one hop.
- Added final send-time validation so manually retained/entered distant destinations cannot be transmitted to.
- Kept selected-channel broadcast available for system-wide messages.

## v0.16 — 2026-08-18

- Added right-click sender actions and navigation between messages and contacts.
- Added blue highlighting for unnamed, requestable 0–1-hop nodes.
- Added gray highlighting and disabled requests for nodes beyond one hop.
- Added full GitHub-ready user, security, troubleshooting, and contribution documentation.

## v0.15

- Persisted hop counts and added hop-aware node-info controls.

## v0.14

- Recognized private PKI topics without attempting channel-key decryption.

## v0.13

- Corrected outbound MeshPacket channel byte to use the XOR channel hash.

## v0.12

- Added NODEINFO requests and manual contact editing.

## v0.11

- Displayed long and short names across the interface.

## v0.10

- Added position lookup, map, and coordinate-copy actions.

## v0.9–v0.9.1

- Added persistent contacts and startup restoration of gateways.

## v0.7–v0.8

- Added encrypted sending, virtual identity, acknowledgements, and location broadcasts.

## v0.1–v0.6

- Initial GUI, configurable MQTT receive, JSON/protobuf decoding, raw packets, and diagnostics.
