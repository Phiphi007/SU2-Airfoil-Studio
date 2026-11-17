"""Scrollable parameter forms for the Tk desktop interface."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ScrollableForm(ttk.Frame):
    """Keep a form within its viewport, with local wheel and keyboard scrolling.

    Wheel bindings belong only to the form's descendants; Matplotlib canvases and
    other tabs retain their own scroll/zoom behavior.
    """

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(
            self, width=1, height=1, highlightthickness=0, borderwidth=0,
            background="#1E1E1E", yscrollincrement=24,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.content = ttk.Frame(self.canvas)
        self.content.columnconfigure(0, weight=1)
        self._window = self.canvas.create_window(0, 0, window=self.content, anchor="nw")
        self.content.bind("<Configure>", self._update_region)
        self.canvas.bind("<Configure>", self._resize_content)

    def _resize_content(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._window, width=max(1, event.width))
        self._update_region()

    def _update_region(self, _event: tk.Event | None = None) -> None:
        self.canvas.configure(scrollregion=(
            0, 0, self.canvas.winfo_width(),
            max(self.content.winfo_reqheight(), self.canvas.winfo_height()),
        ))

    def enable_scrolling(self) -> None:
        """Bind after creating the form fields (no application-wide bindings)."""
        def bind_tree(widget: tk.Misc) -> None:
            widget.bind("<MouseWheel>", self._on_wheel)
            widget.bind("<Button-4>", self._on_wheel)
            widget.bind("<Button-5>", self._on_wheel)
            widget.bind("<FocusIn>", self._on_focus, add="+")
            for child in widget.winfo_children():
                bind_tree(child)

        bind_tree(self.content)
        self.canvas.bind("<MouseWheel>", self._on_wheel)

    def _on_wheel(self, event: tk.Event) -> str:
        delta = getattr(event, "delta", 0)
        if getattr(event, "num", None) == 4:
            units = -3
        elif getattr(event, "num", None) == 5:
            units = 3
        elif delta:
            units = -int(delta / 120) * 3 if abs(delta) >= 120 else (-1 if delta > 0 else 1)
        else:
            return "break"
        self.canvas.yview_scroll(units, "units")
        return "break"

    def _on_focus(self, event: tk.Event) -> None:
        self.reveal(event.widget)

    def reveal(self, widget: tk.Misc) -> None:
        """Expose a field reached by Tab, including fields initially off-screen."""
        top = widget.winfo_rooty() - self.content.winfo_rooty()
        bottom = top + widget.winfo_height()
        visible_top = self.canvas.canvasy(0)
        visible_height = self.canvas.winfo_height()
        target = None
        if top < visible_top:
            target = top - 8
        elif bottom > visible_top + visible_height:
            target = bottom - visible_height + 8
        if target is not None:
            height = max(self.content.winfo_reqheight(), visible_height, 1)
            self.canvas.yview_moveto(max(0, target) / height)


def wrap_to_width(label: tk.Misc) -> None:
    """Wrap explanatory labels using their allocated width, including after translation."""
    def resize(event: tk.Event) -> None:
        width = max(40, event.width - 4)
        if int(float(label.cget("wraplength"))) != width:
            label.configure(wraplength=width)

    label.bind("<Configure>", resize, add="+")
