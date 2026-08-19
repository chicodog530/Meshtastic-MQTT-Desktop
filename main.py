from __future__ import annotations

import json
import hashlib
import queue
import re
import secrets
import ssl
import threading
import time
import tkinter as tk
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk
import tkintermapview
import sv_ttk
import ctypes
import os

import paho.mqtt.client as mqtt

from mqtt_logic import (gateway_from_topic, json_downlink_topic, json_subscription,
                        direct_message_reachable, node_id_to_int, normalize_node_id, parse_json_message,
                        sendtext_envelope)
from protobuf_codec import decode_private_envelope, decode_service_envelope
from protobuf_sender import (build_nodeinfo_envelope, build_nodeinfo_request_envelope,
                             build_position_envelope, build_text_envelope)

APP_NAME = "Meshtastic MQTT Desktop"
CONFIG_FILE = Path.home() / ".meshtastic_mqtt_desktop" / "config.json"
LOG_FILE = CONFIG_FILE.parent / "events.log"
CONTACTS_FILE = CONFIG_FILE.parent / "contacts.json"
DEFAULT = {
    "profile": "LZMesh (Joplin)", "host": "mqtt.lzmesh.com", "port": 1883,
    "username": "meshdev", "password": "large4cats", "root": "msh/LZ",
    "channel_name": "LZMesh", "channel_index": 1, "tls": False,
    "channel_psk": "uLT6S8kQlQHjA7yEtBkzIj3zm6K6lE55mulplDZyF/0=",
    "default_psk": "AQ==",
    "lzrf_psk": "dTEweE82YjhWc1pRS1dzY1FESEk4dnlBcVM2SUxmV3c=",
    "experimental_sending": False,
    "preferred_gateway": "!69b02c8c",
    "virtual_node_id": "", "virtual_long_name": "MQTT Desktop", "virtual_short_name": "MQTT",
    "dark_mode": True,
}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("900x610")
        self.minsize(720, 480)
        self.cfg = self.load_config()
        self.contacts = self.load_contacts()
        self.contacts_save_job = None
        if not self.cfg.get("virtual_node_id"):
            self.cfg["virtual_node_id"] = f"!{(secrets.randbits(32) | 0x80000000):08x}"
            self.save_config()
        self.client: mqtt.Client | None = None
        self.events: queue.Queue = queue.Queue()
        self.gateways: set[str] = set()
        if self.cfg.get("preferred_gateway"):
            self.gateways.add(self.cfg["preferred_gateway"])
        self.raw_messages: dict[str, object] = {}
        self.connected = False
        self.manual_disconnect = False
        self.outgoing: dict[str, float] = {}
        self.outgoing_packet_ids: dict[int, float] = {}
        self.node_names: dict[str, str] = {}
        self.node_rows: dict[str, str] = {}
        self.position_rows: dict[str, str] = {}
        self.seen_packets: dict[tuple, float] = {}
        self.identity_announced: set[tuple[str, str]] = set()
        is_dark = bool(self.cfg.get("dark_mode", True))
        sv_ttk.set_theme("dark" if is_dark else "light")
        self._apply_titlebar_theme(is_dark)
        self._build()
        self._restore_contacts_to_ui()
        self.after(100, self._drain_events)
        self.protocol("WM_DELETE_WINDOW", self.close)

    def load_config(self):
        try:
            return {**DEFAULT, **json.loads(CONFIG_FILE.read_text(encoding="utf-8"))}
        except (OSError, ValueError, TypeError):
            return DEFAULT.copy()

    def save_config(self):
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(self.cfg, indent=2), encoding="utf-8")

    def load_contacts(self):
        try:
            data = json.loads(CONTACTS_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def save_contacts(self):
        self.contacts_save_job = None
        CONTACTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONTACTS_FILE.write_text(json.dumps(self.contacts, indent=2, sort_keys=True), encoding="utf-8")

    def schedule_contacts_save(self):
        if self.contacts_save_job is not None:
            self.after_cancel(self.contacts_save_job)
        self.contacts_save_job = self.after(750, self.save_contacts)

    def _apply_titlebar_theme(self, dark_mode=True):
        if os.name != 'nt':
            return
        try:
            self.update()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            value = ctypes.c_int(2 if dark_mode else 0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
            # Win 11 uses attribute 19
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(value), ctypes.sizeof(value))
        except Exception:
            pass

    def _build(self):
        top = ttk.Frame(self, padding=10); top.pack(fill="x")
        self.status = tk.StringVar(value="Disconnected")
        ttk.Label(top, textvariable=self.status).pack(side="left")
        ttk.Button(top, text="Connect", command=self.connect).pack(side="right", padx=4)
        ttk.Button(top, text="Disconnect", command=self.disconnect).pack(side="right", padx=4)
        ttk.Button(top, text="Settings", command=self.settings).pack(side="right", padx=4)
        ttk.Button(top, text="About", command=self.show_about).pack(side="right", padx=4)
        ttk.Label(top, text="Brought to you by KE0CGB", foreground="gray").pack(side="right", padx=(0, 20))

        notebook = ttk.Notebook(self); notebook.pack(fill="both", expand=True, padx=10)
        self.notebook = notebook
        messages_tab = ttk.Frame(notebook); nodes_tab = ttk.Frame(notebook)
        self.nodes_tab = nodes_tab
        positions_tab = ttk.Frame(notebook); diagnostic_tab = ttk.Frame(notebook)
        map_tab = ttk.Frame(notebook)
        
        notebook.add(messages_tab, text="Messages")
        notebook.add(nodes_tab, text="Nodes")
        notebook.add(positions_tab, text="Positions")
        notebook.add(map_tab, text="Map")
        notebook.add(diagnostic_tab, text="Diagnostics")
        
        self.map_widget = tkintermapview.TkinterMapView(map_tab, corner_radius=0)
        self.map_widget.pack(fill="both", expand=True)
        self.map_markers = {}

        columns = ("time", "direction", "from", "type", "channel", "message", "hops", "rssi", "snr", "gateway")
        self.tree = ttk.Treeview(messages_tab, columns=columns, show="headings")
        widths = (135, 55, 180, 85, 80, 310, 45, 55, 50, 105)
        for col, width in zip(columns, widths):
            self.tree.heading(col, text=col.title()); self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.tag_configure("requestable", foreground="#006fc4")
        self.tree.tag_configure("unreachable", foreground="#777777")
        message_scroll = ttk.Scrollbar(messages_tab, orient="horizontal", command=self.tree.xview)
        self.tree.configure(xscrollcommand=message_scroll.set); message_scroll.pack(fill="x")
        self.tree.bind("<Double-1>", self.show_raw)
        self.tree.bind("<Button-3>", self.show_message_menu)
        self.message_menu = tk.Menu(self, tearoff=False)
        self.message_menu.add_command(label="Request sender's node info", command=self.request_message_sender_nodeinfo)
        self.message_menu.add_command(label="Use sender as destination", command=self.use_message_sender)
        self.message_menu.add_command(label="Show sender in Nodes", command=self.show_message_sender_in_nodes)
        ttk.Button(top, text="View raw packet", command=self.show_raw).pack(side="right", padx=4)

        node_columns = ("node", "name", "short", "hardware", "last_heard", "hops", "gateway", "latitude", "longitude")
        self.nodes_tree = ttk.Treeview(nodes_tab, columns=node_columns, show="headings")
        for col, width in zip(node_columns, (125, 220, 65, 85, 140, 45, 120, 100, 100)):
            self.nodes_tree.heading(col, text=col.replace("_", " ").title()); self.nodes_tree.column(col, width=width, anchor="w")
        self.nodes_tree.pack(fill="both", expand=True)
        self.nodes_tree.tag_configure("requestable", foreground="#006fc4")
        self.nodes_tree.tag_configure("unreachable", foreground="#777777")
        self.nodes_tree.bind("<Double-1>", lambda _event: self.use_selected_contact())
        self.nodes_tree.bind("<<TreeviewSelect>>", lambda _event: self.update_nodeinfo_request_state())
        contacts_bar = ttk.Frame(nodes_tab); contacts_bar.pack(fill="x", pady=5)
        ttk.Label(contacts_bar, text="Blue = unnamed/requestable   Gray = beyond one hop").pack(side="left")
        ttk.Button(contacts_bar, text="Delete contact", command=self.delete_selected_contact).pack(side="right", padx=4)
        ttk.Button(contacts_bar, text="Edit contact", command=self.edit_selected_contact).pack(side="right", padx=4)
        self.request_nodeinfo_button = ttk.Button(contacts_bar, text="Request node info",
                                                  command=self.request_selected_nodeinfo)
        self.request_nodeinfo_button.pack(side="right", padx=4)
        ttk.Button(contacts_bar, text="Use as destination", command=self.use_selected_contact).pack(side="right", padx=4)

        position_columns = ("time", "node", "long_name", "short_name", "latitude", "longitude",
                            "altitude", "place", "gateway")
        self.positions_tree = ttk.Treeview(positions_tab, columns=position_columns, show="headings")
        for col, width in zip(position_columns, (145, 125, 190, 75, 105, 105, 70, 240, 120)):
            self.positions_tree.heading(col, text=col.title()); self.positions_tree.column(col, width=width, anchor="w")
        self.positions_tree.pack(fill="both", expand=True)
        self.position_menu = tk.Menu(self, tearoff=False)
        self.position_menu.add_command(label="Identify location", command=self.identify_selected_position)
        self.position_menu.add_command(label="Open on OpenStreetMap", command=self.open_selected_position)
        self.position_menu.add_command(label="Copy coordinates", command=self.copy_selected_position)
        self.positions_tree.bind("<Button-3>", self.show_position_menu)

        ttk.Label(diagnostic_tab, text=f"Persistent log: {LOG_FILE}", padding=5).pack(fill="x")
        self.log_text = tk.Text(diagnostic_tab, wrap="word", state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=5, pady=(0,5))

        send = ttk.LabelFrame(self, text="Send encrypted Meshtastic text", padding=10); send.pack(fill="x", padx=10, pady=10)
        ttk.Label(send, text="Gateway").grid(row=0, column=0, sticky="w")
        self.gateway = ttk.Combobox(send, width=17, state="normal", values=sorted(self.gateways))
        self.gateway.grid(row=1, column=0, padx=(0,8))
        if self.cfg.get("preferred_gateway"): self.gateway.set(self.cfg["preferred_gateway"])
        ttk.Label(send, text="Channel").grid(row=0, column=1, sticky="w")
        self.send_channel = ttk.Combobox(send, width=12, state="readonly", values=("LZMesh", "LongFast", "LZRF"))
        self.send_channel.set("LZMesh"); self.send_channel.grid(row=1, column=1, padx=(0,8))
        ttk.Label(send, text="Destination").grid(row=0, column=2, sticky="w")
        self.destination = ttk.Combobox(send, width=30, state="normal", values=("Broadcast (selected channel)",))
        self.destination.set("Broadcast (selected channel)"); self.destination.grid(row=1, column=2, padx=(0,8))
        ttk.Label(send, text="Message").grid(row=0, column=3, sticky="w")
        self.message = ttk.Entry(send); self.message.grid(row=1, column=3, sticky="ew", padx=(0,8))
        self.message.bind("<Return>", lambda _e: self.send())
        ttk.Button(send, text="Send", command=self.send).grid(row=1, column=4, padx=(0,8))
        ttk.Button(send, text="Send location…", command=self.send_location_dialog).grid(row=1, column=5)
        ttk.Label(send, text="Direct messages are limited to nodes last heard 0–1 hop from the gateway.",
                  foreground="#666666").grid(row=2, column=0, columnspan=6, sticky="w", pady=(7,0))
        send.columnconfigure(3, weight=1)

    def connect(self):
        self.disconnect()
        self.manual_disconnect = False
        try:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"meshtastic-desktop-{int(time.time()) & 0xffff:x}")
            if self.cfg["username"]:
                client.username_pw_set(self.cfg["username"], self.cfg["password"])
            if self.cfg.get("tls"):
                client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
            client.on_connect = self._on_connect; client.on_disconnect = self._on_disconnect
            client.on_message = self._on_message
            client.reconnect_delay_set(min_delay=2, max_delay=30)
            client.connect_async(self.cfg["host"], int(self.cfg["port"]), 30)
            client.loop_start(); self.client = client
            self.status.set(f"Connecting to {self.cfg['host']}…")
            self._log(f"Connecting to {self.cfg['host']}:{self.cfg['port']}")
        except Exception as exc:
            messagebox.showerror("Connection error", str(exc))

    def disconnect(self):
        self.manual_disconnect = True
        client, self.client = self.client, None
        self.connected = False
        if client:
            try: client.disconnect(); client.loop_stop()
            except Exception: pass
        self.status.set("Disconnected")

    def _on_connect(self, client, _userdata, _flags, reason_code, _properties):
        if reason_code == 0:
            client.subscribe(json_subscription(self.cfg["root"]), qos=0)
            encrypted_topic = f"{self.cfg['root'].strip().strip('/')}/2/e/#"
            client.subscribe(encrypted_topic, qos=0)
            self.events.put(("status", "Connected — listening to JSON + encrypted protobuf"))
            self.events.put(("log", f"Connected; subscribed to JSON and {encrypted_topic}"))
        else: self.events.put(("error", f"Broker rejected connection: {reason_code}"))

    def _on_disconnect(self, _client, _userdata, _flags, reason_code, _properties):
        detail = f"Disconnected: {reason_code}"
        self.events.put(("log", detail))
        if self.manual_disconnect:
            self.events.put(("status", "Disconnected by user"))
        else:
            self.events.put(("status", f"{detail} — reconnecting automatically"))

    def _on_message(self, _client, _userdata, msg):
        try:
            if "/2/e/PKI/" in msg.topic:
                parsed = decode_private_envelope(msg.topic, msg.payload)
            elif "/2/e/" in msg.topic:
                channel = msg.topic.split("/2/e/", 1)[1].split("/", 1)[0]
                preferred = {
                    "LZMesh": self.cfg.get("channel_psk", ""),
                    "LongFast": self.cfg.get("default_psk", "AQ=="),
                    "LZRF": self.cfg.get("lzrf_psk", ""),
                }.get(channel, "")
                keys = [preferred, self.cfg.get("channel_psk", ""),
                        self.cfg.get("default_psk", "AQ=="), self.cfg.get("lzrf_psk", "")]
                parsed = decode_service_envelope(msg.topic, msg.payload, keys)
            else:
                parsed = parse_json_message(msg.topic, msg.payload)
        except Exception as exc:
            self.events.put(("log", f"Could not decode {msg.topic}: {type(exc).__name__}: {exc}"))
            return
        gateway = parsed.gateway_id if parsed else gateway_from_topic(msg.topic)
        if gateway: self.events.put(("gateway", gateway))
        if parsed: self.events.put(("message", parsed))

    def _drain_events(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "status": self.status.set(value); self.connected = value.startswith("Connected")
                elif kind == "error": self.status.set(value); messagebox.showerror("MQTT", value)
                elif kind == "log": self._log(value)
                elif kind == "geocode_result": self._apply_geocode_result(value)
                elif kind == "geocode_error":
                    self.status.set("Location lookup failed")
                    messagebox.showerror("Location lookup", value)
                elif kind == "gateway":
                    self.gateways.add(value); self._refresh_gateway_choices(value if not self.gateway.get() else None)
                elif kind == "message":
                    self.connected = True
                    if not self.status.get().startswith(("Connected", "Published")):
                        self.status.set(f"Connected — receiving from {self.cfg['host']}")
                    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(value.timestamp or time.time()))
                    signature = self._payload_signature(value.raw)
                    now = time.time()
                    packet_key = self._packet_key(value)
                    self.seen_packets = {k: expiry for k, expiry in self.seen_packets.items() if expiry > now}
                    if packet_key and packet_key in self.seen_packets:
                        continue
                    if packet_key:
                        self.seen_packets[packet_key] = now + 600
                    self.outgoing = {k: expiry for k, expiry in self.outgoing.items() if expiry > now}
                    self.outgoing_packet_ids = {k: expiry for k, expiry in self.outgoing_packet_ids.items() if expiry > now}
                    raw_packet_id = value.raw.get("packet", {}).get("id") if isinstance(value.raw.get("packet"), dict) else None
                    direction = "OUT" if signature in self.outgoing or raw_packet_id in self.outgoing_packet_ids else "IN"
                    request_id = value.raw.get("packet", {}).get("request_id") if isinstance(value.raw.get("packet"), dict) else None
                    if value.message_type == "routing" and request_id in self.outgoing_packet_ids:
                        self.status.set(f"Delivery acknowledgement received for packet {request_id:08x}")
                        self._log(f"Meshtastic routing acknowledgement received for packet {request_id:08x}")
                    kind_label = "command" if direction == "OUT" and value.message_type == "sendtext" else value.message_type
                    channel, hops, rssi, snr = self._radio_details(value)
                    sender_display = self._node_label(value.sender)
                    iid = self.tree.insert("", 0, values=(stamp, direction, sender_display, kind_label,
                        channel, value.text, hops, rssi, snr, self._node_label(value.gateway_id)))
                    self.raw_messages[iid] = value
                    self._update_special_views(value, stamp)
                    if len(self.tree.get_children()) > 1000:
                        old = self.tree.get_children()[-1]
                        self.raw_messages.pop(old, None); self.tree.delete(old)
        except queue.Empty: pass
        self.after(100, self._drain_events)

    @staticmethod
    def _packet_key(value):
        if value.raw.get("source") not in ("encrypted-protobuf", "private-pki"):
            return None
        packet = value.raw.get("packet", {})
        packet_id = packet.get("id")
        sender = packet.get("from")
        return (sender, packet_id) if packet_id is not None else None

    @staticmethod
    def _radio_details(value):
        if value.raw.get("source") in ("encrypted-protobuf", "private-pki"):
            packet = value.raw.get("packet", {})
            hop_start = int(packet.get("hop_start", 0) or 0)
            hop_limit = int(packet.get("hop_limit", 0) or 0)
            hops = max(0, hop_start - hop_limit) if hop_start else ""
            return (value.raw.get("channel_id", value.channel), hops,
                    packet.get("rx_rssi", "") or "", packet.get("rx_snr", "") or "")
        raw = value.raw
        return (raw.get("channel", value.channel), raw.get("hops_away", ""),
                raw.get("rssi", ""), raw.get("snr", ""))

    def _update_special_views(self, value, stamp):
        packet = value.raw.get("packet", {})
        decoded = packet.get("decoded", {}) if isinstance(packet, dict) else {}
        node_id = value.sender if re.fullmatch(r"![0-9a-fA-F]{8}", str(value.sender)) else ""
        contact = self.contacts.setdefault(node_id, {}) if node_id else None
        if contact is not None:
            contact.update(last_heard=stamp, gateway=value.gateway_id,
                           channel=value.raw.get("channel_id", value.channel))
            _channel, hops, _rssi, _snr = self._radio_details(value)
            if isinstance(hops, (int, float)) or str(hops).isdigit():
                contact["hops"] = int(hops)
        if value.message_type == "nodeinfo" and isinstance(decoded, dict):
            if packet.get("want_response") and not any(decoded.get(key) for key in
                    ("id", "long_name", "longname", "short_name", "shortname")):
                return
            node_id = decoded.get("id") or value.sender
            long_name = decoded.get("long_name") or decoded.get("longname") or value.text
            short_name = decoded.get("short_name") or decoded.get("shortname") or ""
            self.node_names[node_id] = long_name
            contact = self.contacts.setdefault(node_id, {})
            contact.update(long_name=long_name, short_name=short_name,
                           hardware=decoded.get("hw_model", decoded.get("hardware", "")),
                           last_heard=stamp, gateway=value.gateway_id,
                           channel=value.raw.get("channel_id", value.channel))
            position_row = self.position_rows.get(node_id)
            if position_row:
                position_values = list(self.positions_tree.item(position_row, "values"))
                if len(position_values) >= 9:
                    position_values[2] = long_name; position_values[3] = short_name
                    self.positions_tree.item(position_row, values=position_values)
            self._refresh_named_rows(node_id)
            if "mqtt" in long_name.lower() and "bridge" in long_name.lower():
                self.gateways.add(node_id)
                self._refresh_gateway_choices(node_id)
                self._log(f"Preferred gateway discovered from node info: {long_name} ({node_id})")
            choices = ["Broadcast (selected channel)"]
            choices += [f"{name} ({node})" for node, name in sorted(self.node_names.items(), key=lambda item: item[1].lower())]
            self.destination["values"] = choices
        elif value.message_type == "position" and isinstance(decoded, dict):
            try:
                lat = float(decoded.get("latitude_i", 0)) / 1e7
                lon = float(decoded.get("longitude_i", 0)) / 1e7
            except (TypeError, ValueError):
                return
            contact = self.contacts.setdefault(value.sender, {})
            contact.update(latitude=lat, longitude=lon, altitude=decoded.get("altitude", ""),
                           last_heard=stamp, gateway=value.gateway_id,
                           channel=value.raw.get("channel_id", value.channel))
            values = (stamp, value.sender, contact.get("long_name", ""),
                      contact.get("short_name", ""), f"{lat:.6f}", f"{lon:.6f}",
                      decoded.get("altitude", ""), contact.get("place", ""),
                      self._node_label(value.gateway_id))
            old = self.position_rows.get(value.sender)
            if old: self.positions_tree.item(old, values=values)
            else: self.position_rows[value.sender] = self.positions_tree.insert("", 0, values=values)
            self._update_map_marker(value.sender, lat, lon)
        if contact is not None:
            self._show_contact(node_id, contact)
            self._refresh_sender_tags(node_id)
            self._refresh_destination_choices()
            self.schedule_contacts_save()

    def _contact_values(self, node_id, contact):
        def coordinate(key):
            value = contact.get(key, "")
            return f"{value:.6f}" if isinstance(value, (int, float)) else value
        return (node_id, contact.get("long_name", ""), contact.get("short_name", ""),
                contact.get("hardware", ""), contact.get("last_heard", ""),
                contact.get("hops", ""), self._node_label(contact.get("gateway", "")),
                coordinate("latitude"), coordinate("longitude"))

    def _show_contact(self, node_id, contact):
        values = self._contact_values(node_id, contact)
        tag = self._contact_tag(node_id)
        old = self.node_rows.get(node_id)
        if old: self.nodes_tree.item(old, values=values, tags=(tag,) if tag else ())
        else: self.node_rows[node_id] = self.nodes_tree.insert("", 0, values=values,
                                                               tags=(tag,) if tag else ())

    def _contact_tag(self, node_id):
        contact = self.contacts.get(node_id, {})
        if contact.get("long_name") or contact.get("short_name"): return ""
        hops = contact.get("hops")
        if isinstance(hops, (int, float)):
            return "unreachable" if hops > 1 else "requestable"
        return ""

    def _restore_contacts_to_ui(self):
        for node_id, contact in self.contacts.items():
            name = contact.get("long_name", "")
            if name: self.node_names[node_id] = name
            self._show_contact(node_id, contact)
            if "latitude" in contact and "longitude" in contact:
                values = (contact.get("last_heard", ""), node_id, name,
                          contact.get("short_name", ""),
                          f"{contact['latitude']:.6f}", f"{contact['longitude']:.6f}",
                          contact.get("altitude", ""), contact.get("place", ""),
                          self._node_label(contact.get("gateway", "")))
                self.position_rows[node_id] = self.positions_tree.insert("", "end", values=values)
                self._update_map_marker(node_id, contact['latitude'], contact['longitude'])
            gateway = contact.get("gateway", "")
            if re.fullmatch(r"![0-9a-fA-F]{8}", str(gateway)):
                self.gateways.add(gateway)
        self._refresh_gateway_choices()
        for node_id in self.contacts: self._refresh_named_rows(node_id)
        self._refresh_destination_choices()
        if self.map_markers:
            # Fit map to all markers if there are any
            positions = [(m.position[0], m.position[1]) for m in self.map_markers.values()]
            if positions:
                min_lat = min(p[0] for p in positions); max_lat = max(p[0] for p in positions)
                min_lon = min(p[1] for p in positions); max_lon = max(p[1] for p in positions)
                self.map_widget.fit_bounding_box((max_lat, min_lon), (min_lat, max_lon))
                
    def _update_map_marker(self, node_id, lat, lon):
        label = self._node_label(node_id)
        if node_id in self.map_markers:
            self.map_markers[node_id].set_position(lat, lon)
            self.map_markers[node_id].text = label
        else:
            self.map_markers[node_id] = self.map_widget.set_marker(lat, lon, text=label)
            
    def show_about(self):
        win = tk.Toplevel(self)
        win.title("About")
        win.transient(self)
        win.grab_set()
        win.geometry("350x200")
        win.resizable(False, False)
        
        ttk.Label(win, text=APP_NAME, font=("Segoe UI", 12, "bold")).pack(pady=(20, 5))
        ttk.Label(win, text="Version: 0.18").pack(pady=2)
        ttk.Label(win, text="Developer: KE0CGB LARREN").pack(pady=2)
        
        link = ttk.Label(win, text="GitHub Repository", foreground="blue", cursor="hand2")
        link.pack(pady=10)
        link.bind("<Button-1>", lambda e: webbrowser.open_new("https://github.com/chicodog530/Meshtastic-MQTT-Desktop"))
        
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=15)

    def _refresh_destination_choices(self):
        choices = ["Broadcast (selected channel)"]
        for node_id, contact in sorted(self.contacts.items(),
                key=lambda item: (item[1].get("long_name", "") or item[0]).lower()):
            if direct_message_reachable(contact):
                choices.append(self._node_label(node_id))
        self.destination["values"] = choices
        current = self.destination.get().strip()
        if current and not current.lower().startswith("broadcast"):
            try:
                node_id = self._node_id_from_label(current)
            except ValueError:
                node_id = ""
            if node_id and not direct_message_reachable(self.contacts.get(node_id)):
                self.destination.set("Broadcast (selected channel)")

    def _node_label(self, node_id):
        node_id = str(node_id or "")
        contact = self.contacts.get(node_id, {})
        long_name = contact.get("long_name", "")
        short_name = contact.get("short_name", "")
        if long_name and short_name: return f"{long_name} [{short_name}] ({node_id})"
        if long_name or short_name: return f"{long_name or short_name} ({node_id})"
        return node_id

    @staticmethod
    def _node_id_from_label(label):
        match = re.search(r"![0-9a-fA-F]{8}", str(label))
        if not match: raise ValueError("Enter or select a valid node ID such as !69b02c8c.")
        return normalize_node_id(match.group(0))

    def _refresh_gateway_choices(self, select=None):
        current = select
        if current is None and self.gateway.get():
            match = re.search(r"![0-9a-fA-F]{8}", self.gateway.get())
            current = match.group(0) if match else None
        self.gateway["values"] = [self._node_label(node) for node in sorted(self.gateways)]
        if current: self.gateway.set(self._node_label(current))
        elif self.gateways and not self.gateway.get(): self.gateway.set(self._node_label(sorted(self.gateways)[0]))

    def _refresh_named_rows(self, node_id):
        for row in self.tree.get_children():
            raw = self.raw_messages.get(row)
            if raw is None: continue
            values = list(self.tree.item(row, "values"))
            changed = False
            if raw.sender == node_id:
                values[2] = self._node_label(node_id); changed = True
            if raw.gateway_id == node_id:
                values[9] = self._node_label(node_id); changed = True
            if changed:
                row_tag = self._contact_tag(raw.sender)
                self.tree.item(row, values=values, tags=(row_tag,) if row_tag else ())
        for contact_node, row in self.node_rows.items():
            contact = self.contacts.get(contact_node, {})
            if contact_node == node_id or contact.get("gateway") == node_id:
                self.nodes_tree.item(row, values=self._contact_values(contact_node, contact))
        for contact_node, row in self.position_rows.items():
            contact = self.contacts.get(contact_node, {})
            values = list(self.positions_tree.item(row, "values"))
            if contact_node == node_id and len(values) >= 9:
                values[2] = contact.get("long_name", ""); values[3] = contact.get("short_name", "")
            if contact.get("gateway") == node_id and len(values) >= 9:
                values[8] = self._node_label(node_id)
            self.positions_tree.item(row, values=values)
        self._refresh_gateway_choices()

    def _refresh_sender_tags(self, node_id):
        tag = self._contact_tag(node_id)
        for row, raw in self.raw_messages.items():
            if raw.sender == node_id:
                self.tree.item(row, tags=(tag,) if tag else ())

    def use_selected_contact(self):
        selected = self.nodes_tree.selection()
        if not selected:
            messagebox.showinfo("Choose a contact", "Select a contact in the Nodes tab first."); return
        node_id = self.nodes_tree.item(selected[0], "values")[0]
        contact = self.contacts.get(node_id, {})
        if not direct_message_reachable(contact):
            hops = int(contact["hops"])
            messagebox.showwarning("Node beyond direct-message range",
                f"{self._node_label(node_id)} was last heard {hops} hops away.\n\n"
                "This MQTT gateway is limited to direct messaging nodes one hop away or less.")
            return
        self.destination.set(self._node_label(node_id))
        self.status.set(f"Message destination set to {self._node_label(node_id)}")

    def delete_selected_contact(self):
        selected = self.nodes_tree.selection()
        if not selected: return
        node_id = self.nodes_tree.item(selected[0], "values")[0]
        if not messagebox.askyesno("Delete contact", f"Remove saved contact {node_id}?"): return
        self.contacts.pop(node_id, None)
        self.node_names.pop(node_id, None)
        self.nodes_tree.delete(selected[0]); self.node_rows.pop(node_id, None)
        position_row = self.position_rows.pop(node_id, None)
        if position_row: self.positions_tree.delete(position_row)
        self._refresh_destination_choices(); self.schedule_contacts_save()

    def _selected_contact_id(self):
        selected = self.nodes_tree.selection()
        if not selected:
            messagebox.showinfo("Choose a contact", "Select a contact in the Nodes tab first."); return None
        return str(self.nodes_tree.item(selected[0], "values")[0])

    def update_nodeinfo_request_state(self):
        selected = self.nodes_tree.selection()
        blocked = False
        if selected:
            node_id = str(self.nodes_tree.item(selected[0], "values")[0])
            hops = self.contacts.get(node_id, {}).get("hops")
            blocked = isinstance(hops, (int, float)) and hops > 1
            if blocked:
                self.status.set(f"Node-info request unavailable: {node_id} was last heard {int(hops)} hops away")
        self.request_nodeinfo_button.configure(state="disabled" if blocked else "normal")

    def edit_selected_contact(self):
        node_id = self._selected_contact_id()
        if not node_id: return
        contact = self.contacts.setdefault(node_id, {})
        win = tk.Toplevel(self); win.title(f"Edit contact {node_id}"); win.transient(self); win.grab_set()
        entries = {}
        for row, (label, key) in enumerate((("Long name", "long_name"), ("Short name", "short_name"))):
            ttk.Label(win, text=label).grid(row=row, column=0, sticky="e", padx=8, pady=6)
            entry = ttk.Entry(win, width=32); entry.insert(0, contact.get(key, ""))
            entry.grid(row=row, column=1, padx=8, pady=6); entries[key] = entry
        ttk.Label(win, text="Short names are normally four characters.").grid(
            row=2, column=0, columnspan=2, padx=8, pady=4)
        def save():
            contact["long_name"] = entries["long_name"].get().strip()
            contact["short_name"] = entries["short_name"].get().strip()[:4]
            self.node_names[node_id] = contact["long_name"]
            self._show_contact(node_id, contact); self._refresh_named_rows(node_id)
            self._refresh_destination_choices(); self.schedule_contacts_save(); win.destroy()
        ttk.Button(win, text="Cancel", command=win.destroy).grid(row=3, column=0, sticky="e", padx=8, pady=10)
        ttk.Button(win, text="Save", command=save).grid(row=3, column=1, sticky="e", padx=8, pady=10)

    def request_selected_nodeinfo(self, node_id=None):
        node_id = node_id or self._selected_contact_id()
        if not node_id: return
        hops = self.contacts.get(node_id, {}).get("hops")
        if isinstance(hops, (int, float)) and hops > 1:
            messagebox.showwarning("Node beyond request range",
                f"{self._node_label(node_id)} was last heard {int(hops)} hops away.\n\n"
                "The LZMesh MQTT gateway cannot deliver node-info requests beyond one hop.")
            return
        if not self.cfg.get("experimental_sending"):
            messagebox.showwarning("Sending disabled", "Enable experimental sending in Settings first."); return
        if not self.client or not self.connected:
            messagebox.showwarning("Not connected", "Connect to the broker first."); return
        if not messagebox.askyesno("Request node information",
                f"Request long and short names from {self._node_label(node_id)}?\n\n"
                "The selected MQTT bridge must have an RF route to that node."):
            return
        try:
            gateway = self._node_id_from_label(self.gateway.get())
            channel = self.send_channel.get()
            channel_index, psk = {
                "LZMesh": (1, self.cfg.get("channel_psk", "")),
                "LongFast": (0, self.cfg.get("default_psk", "AQ==")),
                "LZRF": (3, self.cfg.get("lzrf_psk", "")),
            }[channel]
            virtual_node = node_id_to_int(self.cfg["virtual_node_id"])
            topic, payload, packet_id = build_nodeinfo_request_envelope(
                self.cfg["root"], channel, channel_index, psk, virtual_node,
                gateway, node_id_to_int(node_id))
            self.outgoing_packet_ids[packet_id] = time.time() + 300
            info = self.client.publish(topic, payload, qos=0, retain=False)
            if info.rc != mqtt.MQTT_ERR_SUCCESS: raise RuntimeError(mqtt.error_string(info.rc))
            self.status.set(f"Node-info request sent to {self._node_label(node_id)}")
            self._log(f"Requested node info from {node_id} with packet {packet_id:08x} "
                      f"on {channel} via {gateway}")
        except Exception as exc:
            messagebox.showerror("Cannot request node info", str(exc))

    def show_message_menu(self, event):
        row = self.tree.identify_row(event.y)
        if not row: return
        self.tree.selection_set(row); self.tree.focus(row)
        raw = self.raw_messages.get(row)
        node_id = raw.sender if raw else ""
        contact = self.contacts.get(node_id, {})
        named = bool(contact.get("long_name") or contact.get("short_name"))
        hops = contact.get("hops")
        blocked = isinstance(hops, (int, float)) and hops > 1
        self.message_menu.entryconfigure(0, state="disabled" if named or blocked else "normal")
        self.message_menu.entryconfigure(1, state="disabled" if blocked else "normal")
        self.message_menu.tk_popup(event.x_root, event.y_root)

    def _selected_message_sender(self):
        selected = self.tree.selection()
        if not selected: return None
        raw = self.raw_messages.get(selected[0])
        return raw.sender if raw else None

    def request_message_sender_nodeinfo(self):
        node_id = self._selected_message_sender()
        if node_id: self.request_selected_nodeinfo(node_id)

    def use_message_sender(self):
        node_id = self._selected_message_sender()
        if not node_id: return
        contact = self.contacts.get(node_id, {})
        if not direct_message_reachable(contact):
            hops = int(contact["hops"])
            messagebox.showwarning("Node beyond direct-message range",
                f"{self._node_label(node_id)} was last heard {hops} hops away.\n\n"
                "This MQTT gateway is limited to direct messaging nodes one hop away or less.")
            return
        self.destination.set(self._node_label(node_id))
        self.status.set(f"Message destination set to {self._node_label(node_id)}")

    def show_message_sender_in_nodes(self):
        node_id = self._selected_message_sender()
        if not node_id: return
        row = self.node_rows.get(node_id)
        if not row: return
        self.notebook.select(self.nodes_tab)
        self.nodes_tree.selection_set(row); self.nodes_tree.focus(row); self.nodes_tree.see(row)

    def show_position_menu(self, event):
        row = self.positions_tree.identify_row(event.y)
        if not row: return
        self.positions_tree.selection_set(row); self.positions_tree.focus(row)
        self.position_menu.tk_popup(event.x_root, event.y_root)

    def _selected_position(self):
        selected = self.positions_tree.selection()
        if not selected:
            messagebox.showinfo("Choose a position", "Select a position report first."); return None
        values = self.positions_tree.item(selected[0], "values")
        try: return selected[0], str(values[1]), float(values[4]), float(values[5])
        except (IndexError, TypeError, ValueError):
            messagebox.showerror("Position", "That row does not contain valid coordinates."); return None

    def identify_selected_position(self):
        selected = self._selected_position()
        if not selected: return
        _row, node_id, latitude, longitude = selected
        cached = self.contacts.get(node_id, {}).get("place", "")
        if cached:
            messagebox.showinfo("Approximate location", f"{node_id}\n{cached}\n\n{latitude:.6f}, {longitude:.6f}")
            return
        self.status.set(f"Looking up location for {node_id}…")
        threading.Thread(target=self._reverse_geocode,
                         args=(node_id, latitude, longitude), daemon=True).start()

    def _reverse_geocode(self, node_id, latitude, longitude):
        try:
            query = urllib.parse.urlencode({"format": "jsonv2", "lat": latitude,
                                            "lon": longitude, "zoom": 12,
                                            "addressdetails": 1})
            request = urllib.request.Request(
                f"https://nominatim.openstreetmap.org/reverse?{query}",
                headers={"User-Agent": "Meshtastic-MQTT-Desktop/0.10",
                         "Accept-Language": "en"})
            with urllib.request.urlopen(request, timeout=12) as response:
                result = json.loads(response.read().decode("utf-8"))
            address = result.get("address", {})
            locality = next((address.get(key) for key in
                             ("city", "town", "village", "hamlet", "municipality")
                             if address.get(key)), "")
            parts = []
            for part in (locality, address.get("county", ""), address.get("state", ""),
                         address.get("country", "")):
                if part and part not in parts: parts.append(part)
            place = ", ".join(parts) or result.get("display_name", "Unknown location")
            self.events.put(("geocode_result", {"node_id": node_id, "latitude": latitude,
                                                 "longitude": longitude, "place": place}))
        except Exception as exc:
            self.events.put(("geocode_error", f"Could not identify this location.\n\n{exc}"))

    def _apply_geocode_result(self, result):
        node_id = result["node_id"]; place = result["place"]
        contact = self.contacts.setdefault(node_id, {})
        contact["place"] = place; self.schedule_contacts_save()
        row = self.position_rows.get(node_id)
        if row:
            values = list(self.positions_tree.item(row, "values"))
            if len(values) >= 9: values[7] = place
            self.positions_tree.item(row, values=values)
        self.status.set(f"Location identified: {place}")
        messagebox.showinfo("Approximate location",
            f"{node_id}\n{place}\n\n{result['latitude']:.6f}, {result['longitude']:.6f}")

    def open_selected_position(self):
        selected = self._selected_position()
        if not selected: return
        _row, _node_id, latitude, longitude = selected
        webbrowser.open(f"https://www.openstreetmap.org/?mlat={latitude}&mlon={longitude}"
                        f"#map=12/{latitude}/{longitude}")

    def copy_selected_position(self):
        selected = self._selected_position()
        if not selected: return
        _row, _node_id, latitude, longitude = selected
        self.clipboard_clear(); self.clipboard_append(f"{latitude:.6f}, {longitude:.6f}")
        self.status.set("Coordinates copied to clipboard")

    @staticmethod
    def _payload_signature(obj):
        canonical = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _log(self, message):
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"{stamp}  {message}\n"
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with LOG_FILE.open("a", encoding="utf-8") as handle: handle.write(line)
        except OSError: pass
        if hasattr(self, "log_text"):
            self.log_text.configure(state="normal"); self.log_text.insert("end", line)
            self.log_text.see("end"); self.log_text.configure(state="disabled")

    def show_raw(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Raw packet", "Select a message row first."); return
        value = self.raw_messages.get(selected[0])
        if value is None: return
        win = tk.Toplevel(self); win.title("Raw MQTT packet"); win.geometry("760x500")
        ttk.Label(win, text=f"Topic: {value.topic}", padding=8).pack(fill="x")
        text = tk.Text(win, wrap="none", padx=8, pady=8)
        text.insert("1.0", json.dumps(value.raw, indent=2, ensure_ascii=False))
        text.configure(state="disabled"); text.pack(fill="both", expand=True, padx=8, pady=(0,8))

    def send(self):
        if not self.cfg.get("experimental_sending"):
            messagebox.showwarning("Sending disabled",
                "This profile is in receive-only mode. Enable experimental sending in Settings only after confirming a compatible gateway.")
            return
        if not self.client or not self.connected:
            messagebox.showwarning("Not connected", "Connect to the broker first."); return
        try:
            gateway = self._node_id_from_label(self.gateway.get())
            dest_text = self.destination.get().strip()
            destination = None
            if not dest_text.lower().startswith("broadcast"):
                match = re.search(r"![0-9a-fA-F]{8}", dest_text)
                if not match: raise ValueError("Choose Broadcast or enter a node ID such as !433f1c58.")
                destination_id = normalize_node_id(match.group(0))
                contact = self.contacts.get(destination_id)
                if not direct_message_reachable(contact):
                    hops = int(contact["hops"])
                    messagebox.showwarning("Node beyond direct-message range",
                        f"{self._node_label(destination_id)} was last heard {hops} hops away.\n\n"
                        "Direct transmission was not attempted because this MQTT gateway is limited "
                        "to nodes one hop away or less. Choose Broadcast or a 0–1-hop node.")
                    self._refresh_destination_choices()
                    return
                destination = node_id_to_int(destination_id)
            elif not messagebox.askyesno("Confirm system-wide message",
                    f"Broadcast this message to every node on {self.send_channel.get()}?\n\nThis uses the selected MQTT bridge and channel."):
                return
            channel = self.send_channel.get()
            channel_index, psk = {
                "LZMesh": (1, self.cfg.get("channel_psk", "")),
                "LongFast": (0, self.cfg.get("default_psk", "AQ==")),
                "LZRF": (3, self.cfg.get("lzrf_psk", "")),
            }[channel]
            virtual_node = node_id_to_int(self.cfg["virtual_node_id"])
            announcement_key = (gateway, channel)
            if announcement_key not in self.identity_announced:
                info_topic, info_payload, info_id = build_nodeinfo_envelope(
                    self.cfg["root"], channel, channel_index, psk, virtual_node, gateway,
                    self.cfg.get("virtual_long_name", "KE0CGB MQTT"), self.cfg.get("virtual_short_name", "CGB"))
                result = self.client.publish(info_topic, info_payload, qos=0, retain=False)
                if result.rc != mqtt.MQTT_ERR_SUCCESS: raise RuntimeError(mqtt.error_string(result.rc))
                self.outgoing_packet_ids[info_id] = time.time() + 300
                self.identity_announced.add(announcement_key)
                self._log(f"Announced virtual identity {self.cfg['virtual_node_id']} on {channel} via {gateway}")
            topic, payload, packet_id = build_text_envelope(
                self.cfg["root"], channel, channel_index, psk, virtual_node,
                gateway, self.message.get(), destination)
            self.outgoing_packet_ids[packet_id] = time.time() + 300
            info = self.client.publish(topic, payload, qos=0, retain=False)
            if info.rc != mqtt.MQTT_ERR_SUCCESS: raise RuntimeError(mqtt.error_string(info.rc))
            target = "broadcast" if destination is None else f"!{destination:08x}"
            self.message.delete(0, "end"); self.status.set(f"Encrypted text published to {target} via {gateway}; awaiting confirmation")
            self._log(f"Published encrypted text packet {packet_id:08x} to {target} on {channel} via {gateway}")
        except Exception as exc: messagebox.showerror("Cannot send", str(exc))

    def send_location_dialog(self):
        if not self.cfg.get("experimental_sending"):
            messagebox.showwarning("Sending disabled",
                "Enable experimental sending in Settings before publishing a location.")
            return
        win = tk.Toplevel(self); win.title("Send virtual-node location"); win.transient(self); win.grab_set()
        values = {}
        defaults = (("Latitude", "location_latitude"), ("Longitude", "location_longitude"),
                    ("Altitude in metres (optional)", "location_altitude"))
        for row, (label, key) in enumerate(defaults):
            ttk.Label(win, text=label).grid(row=row, column=0, sticky="e", padx=8, pady=6)
            entry = ttk.Entry(win, width=24); entry.insert(0, str(self.cfg.get(key, "")))
            entry.grid(row=row, column=1, padx=8, pady=6); values[key] = entry
        ttk.Label(win, text="This broadcasts the virtual node's location on the selected channel.",
                  foreground="#8a4b00").grid(row=3, column=0, columnspan=2, padx=8, pady=(5,8))

        def publish():
            try:
                latitude = float(values["location_latitude"].get().strip())
                longitude = float(values["location_longitude"].get().strip())
                altitude_text = values["location_altitude"].get().strip()
                altitude = int(altitude_text) if altitude_text else None
                if not messagebox.askyesno("Confirm location broadcast",
                        f"Broadcast location {latitude:.6f}, {longitude:.6f}"
                        + (f" at {altitude} m" if altitude is not None else "")
                        + f" on {self.send_channel.get()}?", parent=win):
                    return
                self._publish_location(latitude, longitude, altitude)
                self.cfg.update(location_latitude=values["location_latitude"].get().strip(),
                                location_longitude=values["location_longitude"].get().strip(),
                                location_altitude=altitude_text)
                self.save_config(); win.destroy()
            except Exception as exc:
                messagebox.showerror("Cannot send location", str(exc), parent=win)

        ttk.Button(win, text="Cancel", command=win.destroy).grid(row=4, column=0, sticky="e", padx=8, pady=10)
        ttk.Button(win, text="Broadcast location", command=publish).grid(row=4, column=1, sticky="e", padx=8, pady=10)

    def _publish_location(self, latitude: float, longitude: float, altitude: int | None):
        if not self.client or not self.connected:
            raise RuntimeError("Connect to the broker first.")
        gateway = self._node_id_from_label(self.gateway.get())
        channel = self.send_channel.get()
        channel_index, psk = {
            "LZMesh": (1, self.cfg.get("channel_psk", "")),
            "LongFast": (0, self.cfg.get("default_psk", "AQ==")),
            "LZRF": (3, self.cfg.get("lzrf_psk", "")),
        }[channel]
        virtual_node = node_id_to_int(self.cfg["virtual_node_id"])
        announcement_key = (gateway, channel)
        if announcement_key not in self.identity_announced:
            info_topic, info_payload, info_id = build_nodeinfo_envelope(
                self.cfg["root"], channel, channel_index, psk, virtual_node, gateway,
                self.cfg.get("virtual_long_name", "KE0CGB MQTT"),
                self.cfg.get("virtual_short_name", "CGB"))
            result = self.client.publish(info_topic, info_payload, qos=0, retain=False)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(mqtt.error_string(result.rc))
            self.outgoing_packet_ids[info_id] = time.time() + 300
            self.identity_announced.add(announcement_key)
            self._log(f"Announced virtual identity {self.cfg['virtual_node_id']} on {channel} via {gateway}")
        topic, payload, packet_id = build_position_envelope(
            self.cfg["root"], channel, channel_index, psk, virtual_node, gateway,
            latitude, longitude, altitude)
        self.outgoing_packet_ids[packet_id] = time.time() + 300
        info = self.client.publish(topic, payload, qos=0, retain=False)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(mqtt.error_string(info.rc))
        self.status.set(f"Location published on {channel} via {gateway}")
        self._log(f"Published position packet {packet_id:08x} ({latitude:.6f}, {longitude:.6f}) "
                  f"on {channel} via {gateway}")

    def settings(self):
        win = tk.Toplevel(self); win.title("Broker settings"); win.transient(self); win.grab_set()
        fields = [("Profile", "profile"), ("Host", "host"), ("Port", "port"), ("Username", "username"),
                  ("Password", "password"), ("Root topic", "root"), ("Channel name", "channel_name"),
                  ("Channel index", "channel_index"), ("LZMesh PSK", "channel_psk"),
                  ("LongFast/default PSK", "default_psk"), ("LZRF PSK", "lzrf_psk"),
                  ("Preferred MQTT gateway", "preferred_gateway"),
                  ("Virtual node ID", "virtual_node_id"), ("Virtual long name", "virtual_long_name"),
                  ("Virtual short name", "virtual_short_name")]
        entries = {}
        for row, (label, key) in enumerate(fields):
            ttk.Label(win, text=label).grid(row=row, column=0, sticky="e", padx=8, pady=5)
            ent = ttk.Entry(win, width=38, show="*" if key in ("password", "channel_psk", "default_psk", "lzrf_psk") else "")
            ent.insert(0, str(self.cfg.get(key, ""))); ent.grid(row=row, column=1, padx=8, pady=5); entries[key] = ent
        tls = tk.BooleanVar(value=bool(self.cfg.get("tls")))
        ttk.Checkbutton(win, text="Use TLS", variable=tls).grid(row=len(fields), column=1, sticky="w", padx=8)
        experimental = tk.BooleanVar(value=bool(self.cfg.get("experimental_sending")))
        ttk.Checkbutton(win, text="Enable experimental sending (receive-only is safer)", variable=experimental).grid(
            row=len(fields)+1, column=1, sticky="w", padx=8, pady=4)
        dark_mode = tk.BooleanVar(value=bool(self.cfg.get("dark_mode", True)))
        ttk.Checkbutton(win, text="Dark Mode", variable=dark_mode).grid(
            row=len(fields)+2, column=1, sticky="w", padx=8, pady=4)
        def save():
            try:
                updated = {k: e.get().strip() for k, e in entries.items()}
                updated["port"] = int(updated["port"]); updated["channel_index"] = int(updated["channel_index"])
                if not 0 <= updated["channel_index"] <= 7: raise ValueError("Channel index must be 0–7")
                updated["tls"] = tls.get(); updated["experimental_sending"] = experimental.get()
                updated["dark_mode"] = dark_mode.get()
                self.cfg.update(updated); self.save_config(); win.destroy()
                sv_ttk.set_theme("dark" if updated["dark_mode"] else "light")
                self._apply_titlebar_theme(updated["dark_mode"])
                if self.connected:
                    self.status.set("Connected — settings saved; reconnect only if connection settings changed")
                else:
                    self.status.set("Settings saved — click Connect")
            except Exception as exc: messagebox.showerror("Invalid settings", str(exc), parent=win)
        ttk.Button(win, text="Save", command=save).grid(row=len(fields)+3, column=1, sticky="e", padx=8, pady=10)

    def close(self):
        if self.contacts_save_job is not None:
            self.after_cancel(self.contacts_save_job)
        try: self.save_contacts()
        except OSError: pass
        self.disconnect(); self.destroy()


if __name__ == "__main__":
    App().mainloop()
