import tkinter as tk
from tkinter import ttk
from ui.components import ToolTip

def build(app, parent):
    messages_tab = ttk.Frame(parent)
    
    columns = ("time", "direction", "from", "type", "channel", "message", "hops", "rssi", "snr", "gateway")
    app.tree = ttk.Treeview(messages_tab, columns=columns, show="headings")
    widths = (135, 55, 180, 85, 80, 310, 45, 55, 50, 105)
    for col, width in zip(columns, widths):
        app.tree.heading(col, text=col.title()); app.tree.column(col, width=width, anchor="w")
    app.tree.pack(fill="both", expand=True)
    app.tree.tag_configure("requestable", foreground="#006fc4")
    app.tree.tag_configure("unreachable", foreground="#777777")
    
    message_scroll = ttk.Scrollbar(messages_tab, orient="horizontal", command=app.tree.xview)
    app.tree.configure(xscrollcommand=message_scroll.set); message_scroll.pack(fill="x")
    app.tree.bind("<Double-1>", app.show_raw)
    app.tree.bind("<Button-3>", app.show_message_menu)
    
    app.message_menu = tk.Menu(app, tearoff=False)
    app.message_menu.add_command(label="Request sender's node info", command=app.request_message_sender_nodeinfo)
    app.message_menu.add_command(label="Use sender as destination", command=app.use_message_sender)
    app.message_menu.add_command(label="Show sender in Nodes", command=app.show_message_sender_in_nodes)
    
    messages_toolbar = ttk.Frame(messages_tab)
    messages_toolbar.pack(fill="x", pady=5)
    ttk.Label(messages_toolbar, text="Tip: Double-click a row to view its raw packet payload").pack(side="left", padx=5)
    btn_raw = ttk.Button(messages_toolbar, text="View raw packet", command=app.show_raw)
    btn_raw.pack(side="right", padx=4)
    ToolTip(btn_raw, "View the raw JSON or Protobuf payload of the selected message", app)
    
    return messages_tab
