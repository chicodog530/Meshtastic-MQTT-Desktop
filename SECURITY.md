# Security

Do not commit private MQTT credentials, private channel PSKs, private keys,
precise location data, or the per-user files stored under
`.meshtastic_mqtt_desktop`. The bundled LZMesh settings are intentionally
published by that network and are not user-specific secrets.

If a credential is accidentally published, remove it from the repository and
rotate it with the MQTT or mesh network administrator immediately.
