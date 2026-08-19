import tkinter as tk
from tkinter import ttk

def build(app, parent):
    nodes_tab = ttk.Frame(parent)
    
    node_columns = ("node", "name", "short", "hardware", "last_heard", "hops", "gateway", "latitude", "longitude")
    app.nodes_tree = ttk.Treeview(nodes_tab, columns=node_columns, show="headings")
    for col, width in zip(node_columns, (125, 220, 65, 85, 140, 45, 120, 100, 100)):
        app.nodes_tree.heading(col, text=col.replace("_", " ").title()); app.nodes_tree.column(col, width=width, anchor="w")
    app.nodes_tree.pack(fill="both", expand=True)
    app.nodes_tree.tag_configure("requestable", foreground="#006fc4")
    app.nodes_tree.tag_configure("unreachable", foreground="#777777")
    app.nodes_tree.bind("<Double-1>", lambda _event: app.use_selected_contact())
    app.nodes_tree.bind("<<TreeviewSelect>>", lambda _event: app.update_nodeinfo_request_state())
    
    contacts_bar = ttk.Frame(nodes_tab); contacts_bar.pack(fill="x", pady=5)
    ttk.Label(contacts_bar, text="Blue = unnamed/requestable   Gray = beyond one hop").pack(side="left")
    ttk.Button(contacts_bar, text="Delete contact", command=app.delete_selected_contact).pack(side="right", padx=4)
    ttk.Button(contacts_bar, text="Edit contact", command=app.edit_selected_contact).pack(side="right", padx=4)
    app.request_nodeinfo_button = ttk.Button(contacts_bar, text="Request node info", command=app.request_selected_nodeinfo)
    app.request_nodeinfo_button.pack(side="right", padx=4)
    ttk.Button(contacts_bar, text="Use as destination", command=app.use_selected_contact).pack(side="right", padx=4)
    
    return nodes_tab
