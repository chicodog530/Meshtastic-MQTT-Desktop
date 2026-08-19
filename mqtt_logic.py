"""Pure helpers for Meshtastic MQTT topics and JSON envelopes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ParsedMessage:
    topic: str
    sender: str
    sender_number: int | None
    gateway_id: str
    message_type: str
    text: str
    timestamp: int | None
    channel: int | None
    raw: dict[str, Any]


def direct_message_reachable(contact: dict[str, Any] | None) -> bool:
    """Return False only when a contact is known to be beyond one RF hop."""
    hops = (contact or {}).get("hops")
    return not (isinstance(hops, (int, float)) and hops > 1)


def message_summary(obj: dict[str, Any]) -> str:
    """Return a useful one-line description for known and unknown JSON shapes."""
    data = obj.get("payload")
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        for key in ("text", "longname", "shortname", "message"):
            if data.get(key):
                return str(data[key])
        if data:
            return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # Some bridges publish decoded fields at the top level instead of payload.
    visible = {k: v for k, v in obj.items()
               if k not in {"from", "to", "sender", "timestamp", "channel", "id", "type"}}
    return json.dumps(visible or obj, ensure_ascii=False, separators=(",", ":"))


def infer_message_type(obj: dict[str, Any]) -> str:
    explicit = obj.get("type")
    if explicit:
        return str(explicit)
    data = obj.get("payload")
    if isinstance(data, dict):
        if "text" in data: return "text"
        if "longname" in data or "shortname" in data: return "nodeinfo"
        if "latitude_i" in data or "longitude_i" in data: return "position"
        if any(k in data for k in ("battery_level", "voltage", "channel_utilization")): return "telemetry"
    packet = obj.get("packet")
    if isinstance(packet, dict):
        decoded = packet.get("decoded")
        if isinstance(decoded, dict) and decoded.get("portnum"):
            return str(decoded["portnum"]).removesuffix("_APP").lower()
        return "meshpacket"
    return "unknown"


def normalize_root(root: str) -> str:
    return root.strip().strip("/")


def normalize_node_id(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if value.startswith("!"):
        value = value[1:]
    if len(value) != 8 or any(c not in "0123456789abcdefABCDEF" for c in value):
        raise ValueError("Node ID must look like !7efeee00 (eight hexadecimal digits).")
    return "!" + value.lower()


def node_id_to_int(node_id: str) -> int:
    return int(normalize_node_id(node_id)[1:], 16)


def gateway_from_topic(topic: str) -> str:
    final = topic.rstrip("/").rsplit("/", 1)[-1]
    try:
        return normalize_node_id(final)
    except ValueError:
        return ""


def json_subscription(root: str) -> str:
    return f"{normalize_root(root)}/2/json/#"


def json_downlink_topic(root: str, channel_name: str, gateway_id: str) -> str:
    channel = channel_name.strip()
    if not channel or "/" in channel:
        raise ValueError("Channel name is required and cannot contain '/'.")
    return f"{normalize_root(root)}/2/json/{channel}/{normalize_node_id(gateway_id)}"


def sendtext_envelope(from_node: int, text: str, channel_index: int = 0,
                      to_node: int | None = None) -> str:
    if not text.strip():
        raise ValueError("Message cannot be empty.")
    if not 0 <= channel_index <= 7:
        raise ValueError("Channel index must be from 0 through 7.")
    body: dict[str, Any] = {
        "from": from_node,
        "channel": channel_index,
        "type": "sendtext",
        "payload": text,
    }
    if to_node is not None:
        body["to"] = to_node
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


def parse_json_message(topic: str, payload: bytes) -> ParsedMessage | None:
    try:
        obj = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(obj, dict):
        return None
    msg_type = infer_message_type(obj)
    text = message_summary(obj)
    sender_number = obj.get("from") if isinstance(obj.get("from"), int) else None
    sender = ""
    if sender_number is not None:
        sender = f"!{sender_number & 0xffffffff:08x}"
    gateway = str(obj.get("sender", ""))
    try:
        gateway = normalize_node_id(gateway) if gateway else gateway_from_topic(topic)
    except ValueError:
        gateway = gateway_from_topic(topic)
    return ParsedMessage(
        topic=topic,
        sender=sender,
        sender_number=sender_number,
        gateway_id=gateway,
        message_type=msg_type,
        text=text,
        timestamp=obj.get("timestamp") if isinstance(obj.get("timestamp"), int) else None,
        channel=obj.get("channel") if isinstance(obj.get("channel"), int) else None,
        raw=obj,
    )
