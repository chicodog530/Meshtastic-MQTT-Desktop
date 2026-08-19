"""Build channel-encrypted Meshtastic text packets for MQTT downlink."""

from __future__ import annotations

import secrets

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from protobuf_codec import decode_psk, expand_key, packet_nonce

BROADCAST = 0xFFFFFFFF


def channel_hash(channel_name: str, psk_text: str) -> int:
    """Return the Meshtastic over-the-air channel hash byte."""
    value = 0
    for byte in channel_name.encode("utf-8") + expand_key(decode_psk(psk_text)):
        value ^= byte
    return value


def _encrypt_packet(packet, psk_text: str, from_node: int):
    plaintext = packet.decoded.SerializeToString()
    key = expand_key(decode_psk(psk_text))
    encryptor = Cipher(algorithms.AES(key), modes.CTR(packet_nonce(packet.id, from_node))).encryptor()
    packet.encrypted = encryptor.update(plaintext) + encryptor.finalize()
    packet.ClearField("decoded")


def _wrap(root: str, channel_name: str, gateway_id: str, virtual_node_id: int, packet):
    from meshtastic import mqtt_pb2
    envelope = mqtt_pb2.ServiceEnvelope()
    envelope.packet.CopyFrom(packet)
    envelope.channel_id = channel_name
    envelope.gateway_id = f"!{virtual_node_id & 0xffffffff:08x}"
    topic = f"{root.strip().strip('/')}/2/e/{channel_name}/{gateway_id}"
    return topic, envelope.SerializeToString(), packet.id


def build_text_envelope(root: str, channel_name: str, channel_index: int,
                        psk_text: str, virtual_node_id: int, gateway_id: str,
                        text: str, destination: int | None = None,
                        hop_limit: int = 3) -> tuple[str, bytes, int]:
    try:
        from meshtastic import mesh_pb2, mqtt_pb2, portnums_pb2
    except ImportError as exc:
        raise RuntimeError("Install the 'meshtastic' package to send protobuf traffic.") from exc

    encoded = text.strip().encode("utf-8")
    if not encoded:
        raise ValueError("Message cannot be empty.")
    if len(encoded) > 220:
        raise ValueError("Message is too long; keep it at 220 UTF-8 bytes or fewer.")
    if not 0 <= channel_index <= 7:
        raise ValueError("Channel index must be between 0 and 7.")

    packet_id = secrets.randbits(32) or 1
    packet = mesh_pb2.MeshPacket()
    setattr(packet, "from", virtual_node_id & 0xffffffff)
    packet.to = BROADCAST if destination is None else destination & 0xffffffff
    packet.id = packet_id
    packet.channel = channel_hash(channel_name, psk_text)
    packet.hop_limit = hop_limit
    packet.hop_start = hop_limit
    packet.want_ack = destination is not None
    packet.decoded.portnum = portnums_pb2.PortNum.TEXT_MESSAGE_APP
    packet.decoded.payload = encoded

    _encrypt_packet(packet, psk_text, virtual_node_id)
    return _wrap(root, channel_name, gateway_id, virtual_node_id, packet)


def build_nodeinfo_envelope(root: str, channel_name: str, channel_index: int,
                            psk_text: str, virtual_node_id: int, gateway_id: str,
                            long_name: str, short_name: str,
                            hop_limit: int = 3) -> tuple[str, bytes, int]:
    from meshtastic import mesh_pb2, portnums_pb2
    packet_id = secrets.randbits(32) or 1
    user = mesh_pb2.User()
    user.id = f"!{virtual_node_id & 0xffffffff:08x}"
    user.long_name = long_name[:24]
    user.short_name = short_name[:4]
    packet = mesh_pb2.MeshPacket()
    setattr(packet, "from", virtual_node_id & 0xffffffff)
    packet.to = BROADCAST; packet.id = packet_id
    packet.channel = channel_hash(channel_name, psk_text)
    packet.hop_limit = hop_limit; packet.hop_start = hop_limit
    packet.decoded.portnum = portnums_pb2.PortNum.NODEINFO_APP
    packet.decoded.payload = user.SerializeToString()
    _encrypt_packet(packet, psk_text, virtual_node_id)
    return _wrap(root, channel_name, gateway_id, virtual_node_id, packet)


def build_position_envelope(root: str, channel_name: str, channel_index: int,
                            psk_text: str, virtual_node_id: int, gateway_id: str,
                            latitude: float, longitude: float,
                            altitude: int | None = None,
                            hop_limit: int = 3) -> tuple[str, bytes, int]:
    """Build a channel-broadcast POSITION_APP packet for the virtual node."""
    from meshtastic import mesh_pb2, portnums_pb2

    if not -90.0 <= latitude <= 90.0:
        raise ValueError("Latitude must be between -90 and 90.")
    if not -180.0 <= longitude <= 180.0:
        raise ValueError("Longitude must be between -180 and 180.")
    if not 0 <= channel_index <= 7:
        raise ValueError("Channel index must be between 0 and 7.")

    position = mesh_pb2.Position()
    position.latitude_i = round(latitude * 10_000_000)
    position.longitude_i = round(longitude * 10_000_000)
    if altitude is not None:
        position.altitude = altitude

    packet_id = secrets.randbits(32) or 1
    packet = mesh_pb2.MeshPacket()
    setattr(packet, "from", virtual_node_id & 0xffffffff)
    packet.to = BROADCAST
    packet.id = packet_id
    packet.channel = channel_hash(channel_name, psk_text)
    packet.hop_limit = hop_limit
    packet.hop_start = hop_limit
    packet.decoded.portnum = portnums_pb2.PortNum.POSITION_APP
    packet.decoded.payload = position.SerializeToString()

    _encrypt_packet(packet, psk_text, virtual_node_id)
    return _wrap(root, channel_name, gateway_id, virtual_node_id, packet)


def build_nodeinfo_request_envelope(root: str, channel_name: str, channel_index: int,
                                    psk_text: str, virtual_node_id: int,
                                    gateway_id: str, destination: int,
                                    hop_limit: int = 3) -> tuple[str, bytes, int]:
    """Request a NODEINFO_APP response from one node."""
    from meshtastic import mesh_pb2, portnums_pb2
    packet_id = secrets.randbits(32) or 1
    packet = mesh_pb2.MeshPacket()
    setattr(packet, "from", virtual_node_id & 0xffffffff)
    packet.to = destination & 0xffffffff
    packet.id = packet_id; packet.channel = channel_hash(channel_name, psk_text)
    packet.hop_limit = hop_limit; packet.hop_start = hop_limit; packet.want_ack = True
    packet.decoded.portnum = portnums_pb2.PortNum.NODEINFO_APP
    packet.decoded.want_response = True
    packet.decoded.payload = b""
    _encrypt_packet(packet, psk_text, virtual_node_id)
    return _wrap(root, channel_name, gateway_id, virtual_node_id, packet)
