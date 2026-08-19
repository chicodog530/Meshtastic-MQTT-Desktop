import tkinter as tk
from tkinter import ttk
from ui.components import ToolTip

def build(app, parent):
    send = ttk.LabelFrame(parent, text="Send encrypted Meshtastic text", padding=10)
    
    ttk.Label(send, text="Gateway").grid(row=0, column=0, sticky="w")
    app.gateway = ttk.Combobox(send, width=25, state="readonly", values=[])
    app.gateway.grid(row=1, column=0, padx=(0,8), sticky="w")
    
    ttk.Label(send, text="Channel").grid(row=0, column=1, sticky="w")
    app.send_channel = ttk.Combobox(send, width=15, state="readonly", values=("LZMesh", "LongFast", "LZRF"))
    app.send_channel.set("LZMesh"); app.send_channel.grid(row=1, column=1, padx=(0,8), sticky="w")
    
    ttk.Label(send, text="Destination").grid(row=0, column=2, sticky="w")
    app.destination = ttk.Combobox(send, width=30, state="normal", values=("Broadcast (selected channel)",))
    app.destination.set("Broadcast (selected channel)"); app.destination.grid(row=1, column=2, padx=(0,8), sticky="ew")
    
    btn_loc = ttk.Button(send, text="Send location…", command=app.send_location_dialog)
    btn_loc.grid(row=1, column=3, sticky="e")
    
    ttk.Label(send, text="Message").grid(row=2, column=0, sticky="w", pady=(10, 0))
    app.message = ttk.Entry(send); app.message.grid(row=3, column=0, columnspan=3, sticky="ew", padx=(0,8))
    app.message.bind("<Return>", lambda _e: app.send())
    
    btn_send = ttk.Button(send, text="Send", command=app.send)
    btn_send.grid(row=3, column=3, sticky="e")
    
    ToolTip(app.gateway, "Select the gateway node to route your message through", app)
    ToolTip(app.send_channel, "Select the Meshtastic channel to broadcast on", app)
    ToolTip(app.destination, "Select the recipient (Broadcast or a specific node)", app)
    ToolTip(btn_loc, "Broadcast your current location to the mesh", app)
    ToolTip(btn_send, "Send the encrypted text message", app)
    
    ttk.Label(send, text="Direct messages are limited to nodes last heard 0–1 hop from the gateway.",
              foreground="#666666").grid(row=4, column=0, columnspan=4, sticky="w", pady=(7,0))
    
    send.columnconfigure(2, weight=1)
    
    return send
