"""Decode encrypted Meshtastic MQTT ServiceEnvelope packets."""

from __future__ import annotations

import base64
import json
import struct
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from mqtt_logic import ParsedMessage


def decode_psk(value: str) -> bytes:
    value = value.strip()
    if value.startswith("base64:"):
        value = value[7:]
    if value.startswith("0x"):
        key = bytes.fromhex(value[2:])
    else:
        try:
            key = base64.b64decode(value, validate=True)
        except Exception:
            key = bytes.fromhex(value)
    if len(key) not in (1, 16, 32):
        raise ValueError("Meshtastic channel PSK must decode to 1, 16, or 32 bytes.")
    return key


def expand_key(key: bytes) -> bytes:
    if len(key) != 1:
        return key
    result = bytearray.fromhex("d4f1bb3a20290759f0bcffabcf4e6901")
    if key[0] > 1:
        result[-1] = (result[-1] + key[0] - 1) & 0xff
    return bytes(result)


def packet_nonce(packet_id: int, from_node: int) -> bytes:
    # Meshtastic uses uint64 packet_id (the uint32 value is zero-extended),
    # followed by uint32 from_node and a zero uint32 AES block counter.
    return struct.pack("<QII", packet_id & 0xffffffff, from_node & 0xffffffff, 0)


def decode_private_envelope(topic: str, payload: bytes) -> ParsedMessage:
    """Expose PKI packet metadata without attempting unavailable private-key decryption."""
    try:
        from meshtastic import mqtt_pb2
    except ImportError as exc:
        raise RuntimeError("Install the 'meshtastic' package to inspect protobuf traffic.") from exc
    envelope = mqtt_pb2.ServiceEnvelope(); envelope.ParseFromString(payload)
    packet = envelope.packet
    from_node = int(getattr(packet, "from"))
    gateway = str(envelope.gateway_id)
    raw = {
        "source": "private-pki",
        "channel_id": str(envelope.channel_id) or "PKI",
        "gateway_id": gateway,
        "packet": {
            "id": int(packet.id), "from": from_node, "to": int(packet.to),
            "channel": int(packet.channel), "hop_limit": int(packet.hop_limit),
            "hop_start": int(packet.hop_start), "rx_rssi": int(packet.rx_rssi),
            "rx_snr": float(packet.rx_snr), "rx_time": int(packet.rx_time),
            "pki_encrypted": True, "encrypted_bytes": len(packet.encrypted),
        },
    }
    return ParsedMessage(
        topic=topic, sender=f"!{from_node & 0xffffffff:08x}", sender_number=from_node,
        gateway_id=gateway, message_type="private",
        text="Private PKI packet — not decryptable by this client",
        timestamp=int(packet.rx_time) or None, channel=int(packet.channel), raw=raw)


def _message_dict(message) -> dict[str, Any]:
    from google.protobuf.json_format import MessageToDict
    return MessageToDict(message, preserving_proto_field_name=True)


def decode_service_envelope(topic: str, payload: bytes, psk_texts: str | list[str]) -> ParsedMessage:
    try:
        from meshtastic import mesh_pb2, mqtt_pb2, portnums_pb2, telemetry_pb2
    except ImportError as exc:
        raise RuntimeError("Install the 'meshtastic' package to decode protobuf traffic.") from exc

    envelope = mqtt_pb2.ServiceEnvelope()
    envelope.ParseFromString(payload)
    packet = envelope.packet
    from_node = int(getattr(packet, "from"))
    packet_id = int(packet.id)

    if packet.HasField("encrypted") and packet.encrypted:
        candidates = [psk_texts] if isinstance(psk_texts, str) else psk_texts
        last_error: Exception | None = None
        for candidate in dict.fromkeys(item for item in candidates if item):
            try:
                key = expand_key(decode_psk(candidate))
                decryptor = Cipher(algorithms.AES(key), modes.CTR(packet_nonce(packet_id, from_node))).decryptor()
                plaintext = decryptor.update(packet.encrypted) + decryptor.finalize()
                trial = mesh_pb2.Data(); trial.ParseFromString(plaintext)
                # Reject lucky garbage parses before accepting a fallback key.
                portnums_pb2.PortNum.Name(trial.portnum)
                if trial.portnum == portnums_pb2.PortNum.UNKNOWN_APP:
                    raise ValueError("decrypted payload has UNKNOWN_APP port")
                packet.decoded.CopyFrom(trial)
                break
            except Exception as exc:
                last_error = exc
        else:
            raise ValueError(f"No configured channel key decrypted this packet ({last_error})")
    elif not packet.HasField("decoded"):
        raise ValueError("MeshPacket contains neither encrypted nor decoded application data.")

    decoded = packet.decoded
    try:
        port_name = portnums_pb2.PortNum.Name(decoded.portnum)
    except ValueError:
        port_name = f"PORT_{decoded.portnum}"
    message_type = port_name.removesuffix("_APP").lower()
    display = ""
    decoded_payload: Any = {"payload_base64": base64.b64encode(decoded.payload).decode("ascii")}

    if decoded.portnum in (portnums_pb2.PortNum.TEXT_MESSAGE_APP,
                           portnums_pb2.PortNum.ALERT_APP,
                           portnums_pb2.PortNum.DETECTION_SENSOR_APP):
        display = decoded.payload.decode("utf-8", errors="replace")
        decoded_payload = {"text": display}
    elif decoded.portnum == portnums_pb2.PortNum.NODEINFO_APP:
        item = mesh_pb2.User(); item.ParseFromString(decoded.payload)
        decoded_payload = _message_dict(item)
        display = item.long_name or item.short_name or item.id
    elif decoded.portnum == portnums_pb2.PortNum.POSITION_APP:
        item = mesh_pb2.Position(); item.ParseFromString(decoded.payload)
        decoded_payload = _message_dict(item)
        latitude = item.latitude_i / 1e7
        longitude = item.longitude_i / 1e7
        display = f"{latitude:.6f}, {longitude:.6f}"
        if item.altitude:
            display += f" — {item.altitude} m"
    elif decoded.portnum == portnums_pb2.PortNum.TELEMETRY_APP:
        item = telemetry_pb2.Telemetry(); item.ParseFromString(decoded.payload)
        decoded_payload = _message_dict(item)
        display = json.dumps(decoded_payload, ensure_ascii=False, separators=(",", ":"))
    elif decoded.portnum == portnums_pb2.PortNum.TRACEROUTE_APP:
        item = mesh_pb2.RouteDiscovery(); item.ParseFromString(decoded.payload)
        decoded_payload = _message_dict(item)
        route = [from_node, *item.route, int(packet.to)]
        display = " → ".join(f"!{node & 0xffffffff:08x}" for node in route)
        if item.route_back:
            back = [int(packet.to), *item.route_back, from_node]
            display += " | back: " + " → ".join(f"!{node & 0xffffffff:08x}" for node in back)
    elif decoded.portnum == portnums_pb2.PortNum.ROUTING_APP:
        display = f"Routing acknowledgement for {decoded.request_id:08x}" if decoded.request_id else "Routing packet"
        decoded_payload = {"request_id": int(decoded.request_id)}
    else:
        display = f"{port_name}, {len(decoded.payload)} payload bytes"

    gateway = str(envelope.gateway_id)
    raw = {
        "source": "encrypted-protobuf",
        "channel_id": str(envelope.channel_id),
        "gateway_id": gateway,
        "packet": {
            "id": packet_id, "from": from_node, "to": int(packet.to),
            "channel": int(packet.channel), "hop_limit": int(packet.hop_limit),
            "hop_start": int(packet.hop_start), "rx_rssi": int(packet.rx_rssi),
            "rx_snr": float(packet.rx_snr), "rx_time": int(packet.rx_time),
            "portnum": port_name, "request_id": int(decoded.request_id), "decoded": decoded_payload,
            "want_response": bool(decoded.want_response),
        },
    }
    return ParsedMessage(
        topic=topic, sender=f"!{from_node & 0xffffffff:08x}", sender_number=from_node,
        gateway_id=gateway, message_type=message_type, text=display,
        timestamp=int(packet.rx_time) or None, channel=int(packet.channel), raw=raw,
    )
