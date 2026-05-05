"""
FBA-Label-Printing-Relic
==================
Dependencies:
    pip install pypdf pymupdf pillow tkinter

Run:
    python FBA_Label_Printing_Relic.py
"""

import os
import io
import threading
import tkinter as tk
from tkinter import filedialog, ttk, scrolledtext
from pathlib import Path
from datetime import datetime

import fitz          # PyMuPDF
from pypdf import PdfWriter, PdfReader
from pypdf.generic import RectangleObject
from PIL import Image, ImageTk


# ─── Crop & rotation config (edit after calibration) ──────────────────────────

CROP_CONFIG = {
    "ups": {
        "enabled":  True,
        "left":     0.0,
        "bottom":   0.05,
        "right":    1.0,
        "top":      0.95,
        "rotation": 90,
    },
    "small_list": {
        "enabled":  True,
        "left":     0.0,
        "bottom":   0.0,
        "right":    1.0,
        "top":      1.0,   # no-op until calibrated
        "rotation": 0,
    },
}


# ─── Classification ────────────────────────────────────────────────────────────

CLASSIFIERS = {
    "tracking_ups":   lambda t: "UPS" in t,
    "tracking_dpd":   lambda t: "DPD" in t,
    "tracking_dhl":   lambda t: "DHL" in t,
    "tracking_fedex": lambda t: any(k in t for k in ("FEDEX", "FedEx")),
    "asn":            lambda t: "ASN" in t,
    "ean":            lambda t: "EAN" in t,
    "small_list":     lambda t: "hoverboard" in t.lower(),
}

TRACKING_TYPES = {"tracking_ups", "tracking_dpd", "tracking_dhl", "tracking_fedex"}

OUTPUT_NAMES = {
    "tracking":     "tracking_list.pdf",
    "asn":          "asn.pdf",
    "ean":          "ean.pdf",
    "small_list":   "small_list.pdf",
    "unclassified": "unclassified.pdf",
}


# ─── Core helpers ─────────────────────────────────────────────────────────────

def extract_text(pdf_path):
    try:
        doc = fitz.open(pdf_path)
        return " ".join(p.get_text() for p in doc)
    except Exception:
        return ""

def classify(text):
    for cls, test in CLASSIFIERS.items():
        if test(text):
            return cls
    return "unclassified"

def group_key(cls):
    return "tracking" if cls in TRACKING_TYPES else cls

def crop_key_for(cls):
    """Return which crop config to use, or None."""
    if cls == "tracking_ups":  return "ups"
    if cls == "small_list":    return "small_list"
    return None

def apply_crop_and_rotation(page, cfg):
    mb = page.mediabox
    w, h = float(mb.width), float(mb.height)
    x0 = w * cfg["left"]
    y0 = h * cfg["bottom"]
    x1 = w * cfg["right"]
    y1 = h * cfg["top"]
    page.mediabox = RectangleObject((x0, y0, x1, y1))
    page.cropbox  = RectangleObject((x0, y0, x1, y1))
    if cfg.get("rotation"):
        page.rotate = cfg["rotation"]
    return page

def build_output_pdf(pages_info, output_path, log):
    writer = PdfWriter()
    for pdf_path, page_idx, ck in pages_info:
        try:
            reader = PdfReader(pdf_path)
            page   = reader.pages[page_idx]
            if ck and CROP_CONFIG[ck]["enabled"]:
                apply_crop_and_rotation(page, CROP_CONFIG[ck])
            writer.add_page(page)
        except Exception as e:
            log(f"    ⚠️  Error on page {page_idx} of {Path(pdf_path).name}: {e}")
    with open(output_path, "wb") as f:
        writer.write(f)

def run_processing(folder, log, progress, done_cb):
    folder_path = Path(folder)
    out_dir = folder_path / "processed"
    out_dir.mkdir(exist_ok=True)

    pdf_files = sorted(folder_path.glob("*.pdf"))
    if not pdf_files:
        log("⚠️  No PDF files found in the selected folder.")
        done_cb(); return

    log(f"📂 Found {len(pdf_files)} PDF file(s)\n")
    buckets = {k: [] for k in OUTPUT_NAMES}
    stats = {"classified": 0, "unclassified": 0}

    for i, pdf_path in enumerate(pdf_files):
        progress(i / len(pdf_files) * 60)
        text = extract_text(str(pdf_path))
        cls  = classify(text)
        key  = group_key(cls)
        ck   = crop_key_for(cls)

        try:
            n = len(PdfReader(str(pdf_path)).pages)
        except Exception as e:
            log(f"  ❌ Cannot read {pdf_path.name}: {e}"); continue

        for pg in range(n):
            buckets[key].append((str(pdf_path), pg, ck))

        if key == "unclassified":
            stats["unclassified"] += 1
            log(f"  ⚠️  UNCLASSIFIED        — {pdf_path.name}")
        else:
            stats["classified"] += 1
            vendor = cls.replace("tracking_", "").upper() if "tracking" in cls else ""
            label  = f"TRACKING ({vendor})" if vendor else key.upper().replace("_", " ")
            crop_note = f" [crop+rot]" if ck else ""
            log(f"  ✅ {label:<22}{crop_note} — {pdf_path.name}")

    log("")
    done_b = 0
    total_b = sum(1 for v in buckets.values() if v)
    for bk, pages_info in buckets.items():
        if not pages_info: continue
        out_path = out_dir / OUTPUT_NAMES[bk]
        try:
            build_output_pdf(pages_info, str(out_path), log)
            log(f"  💾 Saved → {out_path.name}  ({len(pages_info)} page(s))")
        except Exception as e:
            log(f"  ❌ Failed to write {OUTPUT_NAMES[bk]}: {e}")
        done_b += 1
        progress(60 + done_b / max(total_b, 1) * 40)

    log("\n" + "─" * 52)
    log(f"✔  Done at {datetime.now().strftime('%H:%M:%S')}")
    log(f"   Classified   : {stats['classified']} file(s)")
    log(f"   Unclassified : {stats['unclassified']} file(s)")
    log(f"   Output folder: {out_dir}")
    log("─" * 52)
    progress(100)
    done_cb()


# ─── Crop Calibrator Window ───────────────────────────────────────────────────

class CalibratorWindow(tk.Toplevel):
    """
    Opens a PDF page and lets the user drag a crop rectangle.
    On confirm, prints the ratio values and optionally writes them to CROP_CONFIG.
    """
    RENDER_DPI = 120

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Crop Calibrator")
        self.configure(bg="#1e1e2e")
        self.resizable(True, True)

        self._pdf_path = None
        self._page_idx = 0
        self._n_pages  = 0
        self._img_w = self._img_h = 1   # rendered image dimensions
        self._page_w = self._page_h = 1  # original PDF points
        self._photo  = None

        # drag state
        self._drag_start = None
        self._rect_id    = None
        self._rx0 = self._ry0 = self._rx1 = self._ry1 = 0

        self._build()

    def _build(self):
        BG, FG, ACC, BTN = "#1e1e2e", "#cdd6f4", "#89b4fa", "#313244"

        top = tk.Frame(self, bg=BG, pady=8, padx=10)
        top.pack(fill="x")

        tk.Button(top, text="Open PDF…", command=self._open_pdf,
                  bg=ACC, fg="#1e1e2e", font=("Helvetica", 9, "bold"),
                  relief="flat", padx=8, cursor="hand2").pack(side="left")

        self._file_lbl = tk.Label(top, text="No file", bg=BG, fg="#6c7086",
                                  font=("Courier", 9))
        self._file_lbl.pack(side="left", padx=10)

        # page nav
        nav = tk.Frame(top, bg=BG)
        nav.pack(side="right")
        tk.Button(nav, text="◀", command=self._prev_page,
                  bg=BTN, fg=FG, relief="flat", padx=6, cursor="hand2").pack(side="left")
        self._page_lbl = tk.Label(nav, text="—", bg=BG, fg=FG,
                                  font=("Helvetica", 9), width=8)
        self._page_lbl.pack(side="left")
        tk.Button(nav, text="▶", command=self._next_page,
                  bg=BTN, fg=FG, relief="flat", padx=6, cursor="hand2").pack(side="left")

        # target selector
        sel_row = tk.Frame(self, bg=BG, padx=10)
        sel_row.pack(fill="x")
        tk.Label(sel_row, text="Apply to:", bg=BG, fg=FG,
                 font=("Helvetica", 9)).pack(side="left")
        self._target_var = tk.StringVar(value="ups")
        for val, lbl in [("ups", "UPS tracking"), ("small_list", "Small List")]:
            tk.Radiobutton(sel_row, text=lbl, variable=self._target_var, value=val,
                           bg=BG, fg=FG, selectcolor=BTN, activebackground=BG,
                           font=("Helvetica", 9)).pack(side="left", padx=8)

        # rotation
        rot_row = tk.Frame(self, bg=BG, padx=10, pady=4)
        rot_row.pack(fill="x")
        tk.Label(rot_row, text="Rotation (°):", bg=BG, fg=FG,
                 font=("Helvetica", 9)).pack(side="left")
        self._rot_var = tk.IntVar(value=0)
        for r in [0, 90, 180, 270]:
            tk.Radiobutton(rot_row, text=str(r), variable=self._rot_var, value=r,
                           bg=BG, fg=FG, selectcolor=BTN, activebackground=BG,
                           font=("Helvetica", 9)).pack(side="left", padx=6)

        # canvas
        cf = tk.Frame(self, bg="#11111b", padx=6, pady=6)
        cf.pack(fill="both", expand=True, padx=10, pady=6)
        self._canvas = tk.Canvas(cf, bg="#11111b", cursor="crosshair",
                                 highlightthickness=0)
        self._canvas.pack(fill="both", expand=True)
        self._canvas.bind("<ButtonPress-1>",   self._on_press)
        self._canvas.bind("<B1-Motion>",        self._on_drag)
        self._canvas.bind("<ButtonRelease-1>",  self._on_release)

        # ratio readout
        self._ratio_lbl = tk.Label(self, text="Draw a rectangle on the page to set crop area",
                                   bg=BG, fg="#6c7086", font=("Courier", 9))
        self._ratio_lbl.pack(pady=(0, 4))

        # bottom buttons
        bot = tk.Frame(self, bg=BG, padx=10, pady=8)
        bot.pack(fill="x")

        tk.Button(bot, text="Apply to config", command=self._apply,
                  bg="#a6e3a1", fg="#1e1e2e", font=("Helvetica", 9, "bold"),
                  relief="flat", padx=10, cursor="hand2").pack(side="right", padx=(6, 0))

        tk.Button(bot, text="Reset crop", command=self._reset_crop,
                  bg=BTN, fg=FG, font=("Helvetica", 9),
                  relief="flat", padx=10, cursor="hand2").pack(side="right")

        self._status = tk.Label(bot, text="Open a PDF to begin.", bg=BG, fg="#6c7086",
                                font=("Helvetica", 9))
        self._status.pack(side="left")

    # ── File / page ──

    def _open_pdf(self):
        path = filedialog.askopenfilename(
            title="Select a PDF to calibrate",
            filetypes=[("PDF files", "*.pdf")])
        if not path:
            return
        self._pdf_path = path
        self._page_idx = 0
        try:
            doc = fitz.open(path)
            self._n_pages = len(doc)
            doc.close()
        except Exception as e:
            self._status.configure(text=f"Error: {e}"); return
        self._file_lbl.configure(text=Path(path).name)
        self._render_page()

    def _prev_page(self):
        if self._pdf_path and self._page_idx > 0:
            self._page_idx -= 1
            self._render_page()

    def _next_page(self):
        if self._pdf_path and self._page_idx < self._n_pages - 1:
            self._page_idx += 1
            self._render_page()

    def _render_page(self):
        if not self._pdf_path:
            return
        doc  = fitz.open(self._pdf_path)
        page = doc[self._page_idx]
        mat  = fitz.Matrix(self.RENDER_DPI / 72, self.RENDER_DPI / 72)
        pix  = page.get_pixmap(matrix=mat, alpha=False)
        self._page_w = page.rect.width
        self._page_h = page.rect.height
        doc.close()

        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        # fit to canvas
        self.update_idletasks()
        cw = max(self._canvas.winfo_width(),  400)
        ch = max(self._canvas.winfo_height(), 500)
        img.thumbnail((cw, ch), Image.LANCZOS)
        self._img_w, self._img_h = img.size
        self._photo = ImageTk.PhotoImage(img)
        self._canvas.delete("all")
        ox = (cw - self._img_w) // 2
        oy = (ch - self._img_h) // 2
        self._img_offset = (ox, oy)
        self._canvas.create_image(ox, oy, anchor="nw", image=self._photo)
        self._page_lbl.configure(
            text=f"{self._page_idx+1} / {self._n_pages}")
        self._rect_id = None
        self._status.configure(text="Drag to select crop area.")

    # ── Drag ──

    def _on_press(self, e):
        self._drag_start = (e.x, e.y)
        if self._rect_id:
            self._canvas.delete(self._rect_id)
            self._rect_id = None

    def _on_drag(self, e):
        if not self._drag_start:
            return
        x0, y0 = self._drag_start
        if self._rect_id:
            self._canvas.delete(self._rect_id)
        self._rect_id = self._canvas.create_rectangle(
            x0, y0, e.x, e.y,
            outline="#f38ba8", width=2, dash=(4, 3))
        self._rx0, self._ry0 = x0, y0
        self._rx1, self._ry1 = e.x, e.y
        self._update_ratios()

    def _on_release(self, e):
        self._drag_start = None

    def _update_ratios(self):
        if not hasattr(self, "_img_offset"):
            return
        ox, oy = self._img_offset
        # clamp to image bounds
        x0 = max(0, min(self._rx0, self._rx1) - ox) / self._img_w
        x1 = max(0, min(max(self._rx0, self._rx1) - ox, self._img_w)) / self._img_w
        # PDF y-axis is bottom-up; canvas is top-down
        y_top_canvas    = min(self._ry0, self._ry1)
        y_bottom_canvas = max(self._ry0, self._ry1)
        top    = 1.0 - max(0, y_top_canvas - oy) / self._img_h
        bottom = 1.0 - max(0, min(y_bottom_canvas - oy, self._img_h)) / self._img_h

        self._ratios = dict(left=round(x0,4), bottom=round(bottom,4),
                            right=round(x1,4), top=round(top,4))
        self._ratio_lbl.configure(
            text=f"left={x0:.3f}  bottom={bottom:.3f}  "
                 f"right={x1:.3f}  top={top:.3f}")

    def _reset_crop(self):
        if self._rect_id:
            self._canvas.delete(self._rect_id)
            self._rect_id = None
        self._ratios = dict(left=0.0, bottom=0.0, right=1.0, top=1.0)
        self._ratio_lbl.configure(text="Crop reset to full page.")

    def _apply(self):
        if not hasattr(self, "_ratios"):
            self._status.configure(text="⚠️  Draw a crop rectangle first.")
            return
        target = self._target_var.get()
        CROP_CONFIG[target].update({
            **self._ratios,
            "rotation": self._rot_var.get(),
            "enabled":  True,
        })
        r = self._ratios
        self._status.configure(
            text=f"✔ Applied to [{target}] — "
                 f"L={r['left']:.3f} B={r['bottom']:.3f} "
                 f"R={r['right']:.3f} T={r['top']:.3f}  rot={self._rot_var.get()}°")


# ─── Main GUI ─────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FBA-Label-Printing-Relic")
        self.geometry("740x580")
        self.resizable(True, True)
        self.configure(bg="#1e1e2e")
        self._build()

    def _build(self):
        PAD = 12
        BG  = "#1e1e2e"
        FG  = "#cdd6f4"
        ACC = "#89b4fa"
        BTN = "#313244"

        # header
        hdr = tk.Frame(self, bg="#181825", pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="📄 FBA-Label-Printing-Relic", font=("Helvetica", 16, "bold"),
                 bg="#181825", fg=ACC).pack()
        tk.Label(hdr, text="Classify · Crop · Rotate · Merge",
                 font=("Helvetica", 9), bg="#181825", fg="#6c7086").pack()

        # folder row
        row = tk.Frame(self, bg=BG, pady=PAD)
        row.pack(fill="x", padx=PAD)
        self.folder_var = tk.StringVar(value="No folder selected")
        tk.Label(row, textvariable=self.folder_var, bg=BTN, fg=FG,
                 anchor="w", padx=8, font=("Courier", 9),
                 relief="flat").pack(side="left", fill="x", expand=True, ipady=6)
        tk.Button(row, text="Browse…", command=self._browse,
                  bg=ACC, fg="#1e1e2e", font=("Helvetica", 9, "bold"),
                  relief="flat", padx=10, cursor="hand2").pack(side="left", padx=(8, 0))

        # legend
        leg = tk.Frame(self, bg=BG)
        leg.pack(fill="x", padx=PAD, pady=(0, 6))
        for txt, col in [("🟦 Tracking", ACC), ("🟩 ASN", "#a6e3a1"),
                         ("🟨 EAN", "#f9e2af"), ("🟪 Small List", "#cba6f7"),
                         ("🟥 Unclassified", "#f38ba8")]:
            tk.Label(leg, text=txt, bg=BG, fg=col,
                     font=("Helvetica", 8)).pack(side="left", padx=6)

        # log
        self.log_box = scrolledtext.ScrolledText(
            self, bg="#11111b", fg=FG, font=("Courier", 9),
            relief="flat", state="disabled", wrap="word")
        self.log_box.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))

        # bottom bar
        bot = tk.Frame(self, bg=BG)
        bot.pack(fill="x", padx=PAD, pady=(0, PAD))
        self.progress = ttk.Progressbar(bot, mode="determinate", maximum=100)
        self.progress.pack(fill="x", side="top", pady=(0, 8))

        btn_row = tk.Frame(bot, bg=BG)
        btn_row.pack(fill="x")
        self.status_lbl = tk.Label(btn_row, text="Ready.", bg=BG, fg="#6c7086",
                                   font=("Helvetica", 9))
        self.status_lbl.pack(side="left")

        tk.Button(btn_row, text="✂  Crop Calibrator", command=self._open_calibrator,
                  bg=BTN, fg=FG, font=("Helvetica", 9),
                  relief="flat", padx=10, pady=4, cursor="hand2").pack(side="right", padx=(6, 0))

        self.run_btn = tk.Button(
            btn_row, text="▶  Run Processing", command=self._run,
            bg="#a6e3a1", fg="#1e1e2e", font=("Helvetica", 10, "bold"),
            relief="flat", padx=16, pady=4, cursor="hand2")
        self.run_btn.pack(side="right")

    def _browse(self):
        folder = filedialog.askdirectory(title="Select PDF folder")
        if folder:
            self.folder_var.set(folder)
            self._log(f"📂 Selected: {folder}\n")

    def _log(self, msg):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _set_progress(self, val):
        self.progress["value"] = val
        self.update_idletasks()

    def _open_calibrator(self):
        CalibratorWindow(self)

    def _run(self):
        folder = self.folder_var.get()
        if folder == "No folder selected" or not os.path.isdir(folder):
            self._log("⚠️  Please select a valid folder first.")
            return
        self.run_btn.configure(state="disabled", text="⏳ Processing…")
        self.status_lbl.configure(text="Processing…")
        self.progress["value"] = 0
        self._log("=" * 52)
        self._log(f"🚀 Starting at {datetime.now().strftime('%H:%M:%S')}")
        self._log("=" * 52)

        def on_done():
            self.run_btn.configure(state="normal", text="▶  Run Processing")
            self.status_lbl.configure(text="Done ✔")

        threading.Thread(
            target=run_processing,
            args=(folder, self._log, self._set_progress, on_done),
            daemon=True
        ).start()


if __name__ == "__main__":
    app = App()
    app.mainloop()
