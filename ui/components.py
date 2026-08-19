import tkinter as tk
from tkinter import ttk

class ToolTip:
    def __init__(self, widget, text, app):
        self.widget = widget
        self.text = text
        self.app = app
        self.tipwindow = None
        self.id = None
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)

    def enter(self, event=None):
        if not bool(self.app.cfg.get("show_tooltips", True)): return
        self.unschedule()
        self.id = self.widget.after(500, self.showtip)

    def leave(self, event=None):
        self.unschedule()
        self.hidetip()

    def unschedule(self):
        id = self.id
        self.id = None
        if id: self.widget.after_cancel(id)

    def showtip(self, event=None):
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        
        is_dark = bool(self.app.cfg.get("dark_mode", True))
        bg = "#333333" if is_dark else "#ffffe0"
        fg = "white" if is_dark else "black"
        
        label = tk.Label(tw, text=self.text, justify="left",
                         background=bg, foreground=fg, relief="solid", borderwidth=1,
                         font=("Segoe UI", "9", "normal"))
        label.pack(ipadx=4, ipady=2)
        
    def hidetip(self):
        tw = self.tipwindow
        self.tipwindow = None
        if tw: tw.destroy()
