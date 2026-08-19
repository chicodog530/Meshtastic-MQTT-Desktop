import tkinter as tk
from tkinter import ttk

def build(app, parent):
    diagnostic_tab = ttk.Frame(parent)
    
    ttk.Label(diagnostic_tab, text="Persistent log: message_log.txt", padding=5).pack(fill="x")
    app.log_text = tk.Text(diagnostic_tab, wrap="word", state="disabled")
    app.log_text.pack(fill="both", expand=True, padx=5, pady=(0,5))
    
    return diagnostic_tab
