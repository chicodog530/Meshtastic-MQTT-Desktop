import tkinter as tk
from tkinter import ttk
import tkintermapview

def build(app, parent):
    map_tab = ttk.Frame(parent)
    
    map_toolbar = ttk.Frame(map_tab); map_toolbar.pack(fill="x", pady=2)
    ttk.Button(map_toolbar, text="Pop out map (Fullscreen)", command=app.popout_map).pack(side="right", padx=5)
    
    app.map_widget = tkintermapview.TkinterMapView(map_tab, corner_radius=0)
    app.map_widget.set_tile_server("https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png")
    app.map_widget.pack(fill="both", expand=True)
    app.map_markers = {}
    
    return map_tab
