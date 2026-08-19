# Troubleshooting Guide

## Collecting useful information

Open Diagnostics and note the broker connection, subscription, and exact error. The persistent log is under `.meshtastic_mqtt_desktop` in your home directory. Remove credentials, private keys/messages, and precise coordinates before sharing it.

## Environment checks

Windows:

```powershell
py --version
.venv\Scripts\python.exe -m pip show paho-mqtt meshtastic cryptography
.venv\Scripts\python.exe -c "import tkinter; print('Tkinter OK')"
```

Linux:

```bash
python3 --version
.venv/bin/python -m pip show paho-mqtt meshtastic cryptography
.venv/bin/python -c "import tkinter; print('Tkinter OK')"
```

## Connection failures

- **Name resolution/timeout:** verify the broker hostname and internet connection.
- **Not authorized:** recheck username, password, and broker ACLs.
- **TLS error:** match TLS and port to the broker configuration.
- **Immediate disconnect:** check unique client-ID, TLS, and protocol requirements.

## Decode failures

- Confirm the packet's channel key and name are configured.
- Reinstall dependencies into the environment used to launch the app.
- PKI/private packets cannot be decrypted with shared channel keys.
- Preserve the raw topic/payload for a parser report after removing private data.

## Transmission failures

Successful MQTT publication is not proof of RF receipt. Verify the gateway is online, downlink-enabled, on the correct channel, in RF range, allowed to retransmit, and experimental sending is enabled.

LZMesh NODEINFO requests beyond one hop are intentionally disabled because the bridge is not expected to deliver them.

## Resetting local state

Close the app and rename `.meshtastic_mqtt_desktop` in your home folder. Restarting creates fresh defaults. Retain the renamed folder until any desired contacts or configuration have been recovered.
