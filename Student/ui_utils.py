import customtkinter as ctk

COLORS = {
    "navy": "#2b1745",
    "navy_panel": "#493064",
    "blue": "#55b9e8",
    "blue_hover": "#319dce",
    "sky": "#55b9e8",
    "pink": "#e76aa9",
    "pink_hover": "#ca4e90",
    "surface": "#fbf7fc",
    "surface_alt": "#f0e8f5",
    "ink": "#2e2340",
    "muted": "#786b88",
    "white": "#ffffff",
    "danger": "#df4f92",
    "success": "#269fc4",
}


def apply_theme():
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")


def maximize_window(window):
    window.after(50, lambda: window.state("zoomed"))


def center_window(win, width, height):
    """Centers any Tk/CTk window (main window or Toplevel) on the screen,
    and sets its size. Call this instead of win.geometry('WxH')."""
    win.update_idletasks()
    screen_w = win.winfo_screenwidth()
    screen_h = win.winfo_screenheight()
    x = (screen_w - width) // 2
    y = (screen_h - height) // 2
    win.geometry(f"{width}x{height}+{x}+{y}")