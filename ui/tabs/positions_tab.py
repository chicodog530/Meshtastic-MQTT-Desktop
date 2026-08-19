import tkinter as tk
from tkinter import ttk

def build(app, parent):
    positions_tab = ttk.Frame(parent)
    
    position_columns = ("time", "node", "long_name", "short_name", "latitude", "longitude",
                        "altitude", "place", "gateway")
    app.positions_tree = ttk.Treeview(positions_tab, columns=position_columns, show="headings")
    for col, width in zip(position_columns, (145, 125, 190, 75, 105, 105, 70, 240, 120)):
        app.positions_tree.heading(col, text=col.title()); app.positions_tree.column(col, width=width, anchor="w")
    app.positions_tree.pack(fill="both", expand=True)
    pos_scroll = ttk.Scrollbar(positions_tab, orient="horizontal", command=app.positions_tree.xview)
    app.positions_tree.configure(xscrollcommand=pos_scroll.set); pos_scroll.pack(fill="x")

    app.position_menu = tk.Menu(app, tearoff=False)
    app.position_menu.add_command(label="Identify location", command=app.identify_selected_position)
    app.position_menu.add_command(label="Open on OpenStreetMap", command=app.open_selected_position)
    app.position_menu.add_command(label="Copy coordinates", command=app.copy_selected_position)
    app.positions_tree.bind("<Button-3>", app.show_position_menu)
    
    return positions_tab
