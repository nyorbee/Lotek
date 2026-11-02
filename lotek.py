# -*- coding: utf-8 -*-
"""
Lotek – losowarka liczb do gier liczbowych.

Losowanie: kryptograficzny generator systemu (secrets.SystemRandom),
liczby bez powtórzeń, zakres z obiema granicami włącznie, wynik rosnąco.

Kule rysowane są przez Pillow (wygładzone krawędzie, styl płaski),
animacja: kule spadają na swoje miejsca z odbiciem (~60 kl./s).

Wymaga:  pip install pillow

Build (Nuitka, onefile z cache – rozpakowuje się tylko raz):
    python -m nuitka --onefile --enable-plugin=tk-inter --windows-console-mode=disable
      --windows-icon-from-ico=lotek.ico
      --include-data-files=created.png=created.png --company-name=nyorbee --product-name=Lotek
      --product-version=1.3 --onefile-tempdir-spec="{CACHE_DIR}/{COMPANY}/{PRODUCT}/{VERSION}"
      --onefile-cache-mode=cached --assume-yes-for-downloads --output-filename=Lotek.exe lotek.py
"""

import base64
import io
import math
import os
import sys
import webbrowser
import secrets
import time
import tkinter as tk
from tkinter import font as tkfont

from PIL import Image, ImageDraw, ImageFilter, ImageFont

RNG = secrets.SystemRandom()

AUTHOR_URL = "https://www.facebook.com/ajtiguy"


def resource_path(name):
    """Plik obok skryptu / wewnątrz exe Nuitki (fallback: obok exe)."""
    for base in (os.path.dirname(os.path.abspath(__file__)),
                 os.path.dirname(os.path.abspath(sys.argv[0]))):
        p = os.path.join(base, name)
        if os.path.exists(p):
            return p
    return None

MAX_CUSTOM_COUNT = 60      # maks. liczb w trybie "Własne"
MAX_CUSTOM_VALUE = 9999    # maks. wartość "Do" w trybie "Własne"

# ----------------------------------------------------------------- gry ---
GAMES = [
    dict(key="duzy",    name="Duży Lotek",    sub="6 z 49",          lo=1, hi=49, count=6),
    dict(key="szybkie", name="Szybkie 600",   sub="6 z 32",          lo=1, hi=32, count=6),
    dict(key="euro",    name="Eurojackpot",   sub="5 z 50 + 2 z 12", lo=1, hi=50, count=5,
         extra=dict(lo=1, hi=12, count=2, label="Euro liczby")),
    dict(key="keno",    name="Keno",          sub="1–10 z 70",       lo=1, hi=70, count=10, choose=True),
    dict(key="multi",   name="Multi Multi",   sub="1–10 z 80",       lo=1, hi=80, count=10, choose=True),
    dict(key="pensja",  name="Ekstra Pensja", sub="5 z 35 + 1 z 4",  lo=1, hi=35, count=5,
         extra=dict(lo=1, hi=4, count=1, label="Liczba dodatkowa")),
    dict(key="mini",    name="Mini Lotto",    sub="5 z 42",          lo=1, hi=42, count=5),
    dict(key="wlasne",  name="Własne",        sub="Twój zakres",     custom=True),
]

# -------------------------------------------------------------- kolory ---
BG          = "#FFF8E1"
RED         = "#E30613"
RED_DARK    = "#B4050F"
YELLOW      = "#FFC72C"
BLUE        = "#0B3D91"
BLUE_BALL   = "#1E5BC6"
DARK        = "#1A1A2E"
CARD        = "#FFFDF6"
GRID        = "#F7DCDC"
MUTED       = "#8A8371"
GREEN       = "#2EAD4B"
ORANGE      = "#FF8A00"


def draw_numbers(lo, hi, count):
    """Losuje `count` różnych liczb z [lo, hi] włącznie, zwraca posortowane."""
    return sorted(RNG.sample(range(lo, hi + 1), count))


def liczb(n):
    """1 liczba, 2 liczby, 5 liczb, 22 liczby…"""
    if n == 1:
        return "1 liczba"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} liczby"
    return f"{n} liczb"


def _mix(hex_color, target, t):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    tr, tg, tb = target
    r = round(r + (tr - r) * t); g = round(g + (tg - g) * t); b = round(b + (tb - b) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def lighten(c, t): return _mix(c, (255, 255, 255), t)
def darken(c, t):  return _mix(c, (0, 0, 0), t)


def _rgb(c):
    h = c.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def ease_out_bounce(t):
    n, d = 7.5625, 2.75
    if t < 1 / d:
        return n * t * t
    if t < 2 / d:
        t -= 1.5 / d
        return n * t * t + 0.75
    if t < 2.5 / d:
        t -= 2.25 / d
        return n * t * t + 0.9375
    t -= 2.625 / d
    return n * t * t + 0.984375


class BallArt:
    """Rysuje wygładzone, cieniowane kule (Pillow) i trzyma je w cache."""
    SS = 4  # supersampling

    FONT_FILES = ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                  "/System/Library/Fonts/Supplemental/Arial Bold.ttf")

    def __init__(self):
        self.cache = {}
        self.fonts = {}
        self.font_file = None
        for f in self.FONT_FILES:
            try:
                ImageFont.truetype(f, 10)
                self.font_file = f
                break
            except OSError:
                continue

    def _font(self, size):
        if size not in self.fonts:
            if self.font_file:
                self.fonts[size] = ImageFont.truetype(self.font_file, size)
            else:
                try:
                    self.fonts[size] = ImageFont.load_default(size)
                except TypeError:
                    self.fonts[size] = ImageFont.load_default()
        return self.fonts[size]

    @staticmethod
    def _to_tk(img):
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return tk.PhotoImage(data=base64.b64encode(buf.getvalue()))

    def ball(self, num, color, d):
        key = ("b", num, color, d)
        if key not in self.cache:
            self.cache[key] = self._to_tk(self._render_ball(num, color, d))
        return self.cache[key]

    def shadow(self, d, level, levels):
        key = ("s", d, level)
        if key not in self.cache:
            self.cache[key] = self._to_tk(self._render_shadow(d, level / levels))
        return self.cache[key]

    def _render_ball(self, num, color, d):
        """Styl płaski: delikatny pionowy gradient, jasna obwódka, wyraźny numer."""
        S = d * self.SS
        c = S / 2
        base = _rgb(color)
        top, bottom = _lerp(base, (255, 255, 255), 0.18), _lerp(base, (0, 0, 0), 0.12)

        grad = Image.new("RGB", (S, S))
        gd = ImageDraw.Draw(grad)
        for y in range(S):
            gd.line([(0, y), (S, y)], fill=_lerp(top, bottom, y / (S - 1)))
        mask = Image.new("L", (S, S), 0)
        ImageDraw.Draw(mask).ellipse([1, 1, S - 2, S - 2], fill=255)
        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        img.paste(grad, (0, 0), mask)

        dr = ImageDraw.Draw(img)
        r = S * 0.40
        dr.ellipse([c - r, c - r, c + r, c + r], outline=(255, 255, 255, 125), width=max(1, int(S * 0.018)))

        lum = 0.299 * base[0] + 0.587 * base[1] + 0.114 * base[2]
        ink = _rgb(DARK) if lum > 160 else (255, 255, 255)
        s = str(num)
        k = {1: 0.44, 2: 0.36, 3: 0.27, 4: 0.21}.get(len(s), 0.17)
        dr.text((c, c + S * 0.01), s, font=self._font(int(S * k)), fill=ink, anchor="mm")
        return img.resize((d, d), Image.LANCZOS)

    def _render_shadow(self, d, strength):
        w, h = int(d * 1.1), int(d * 0.42)
        S = self.SS
        img = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
        a = int(95 * strength)
        sw = 0.55 + 0.45 * strength  # cień rośnie, gdy kula się zbliża
        cx, cy = w * S / 2, h * S / 2
        rx, ry = w * S * 0.40 * sw, h * S * 0.26 * sw
        ImageDraw.Draw(img).ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=(70, 50, 20, a))
        img = img.filter(ImageFilter.GaussianBlur(h * S * 0.12))
        return img.resize((w, h), Image.LANCZOS)


def pick_family(root):
    fams = set(tkfont.families(root))
    for f in ("Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans"):
        if f in fams:
            return f
    return "TkDefaultFont"


# ================================================================ App ====
class LotekApp:
    W = 780  # szerokość okna w px (przed skalowaniem DPI)

    def __init__(self, root):
        self.root = root
        self.s = max(1.0, root.winfo_fpixels("1i") / 96.0)
        self.fam = pick_family(root)
        self.art = BallArt()
        self.anim_job = None
        self.anim = []
        self.animating = False
        self.result = None
        self.game = None
        self.tiles = {}

        self.choose_vars = {g["key"]: tk.IntVar(value=g["count"])
                            for g in GAMES if g.get("choose")}
        self.c_from = tk.StringVar(value="1")
        self.c_to = tk.StringVar(value="49")
        self.c_count = tk.StringVar(value="6")

        root.title("Lotek – losowarka liczb")
        root.configure(bg=BG)
        root.resizable(False, False)
        try:
            self._icon = tk.PhotoImage(data=ICON_PNG)
            root.iconphoto(True, self._icon)
        except tk.TclError:
            pass

        self._build_header()
        self._build_presets()
        self._build_options()
        self._build_draw_button()
        self._build_result()
        self._build_footer()

        self.select_game(GAMES[0])
        root.bind("<Return>", lambda e: self.on_draw())
        root.bind("<KP_Enter>", lambda e: self.on_draw())

    # ---------------------------------------------------------- helpers --
    def px(self, v):
        return int(round(v * self.s))

    def f(self, size_px, weight="normal"):
        return (self.fam, -self.px(size_px), weight)

    def cancel_animation(self):
        if self.anim_job:
            try:
                self.root.after_cancel(self.anim_job)
            except tk.TclError:
                pass
        self.anim_job = None
        self.anim = []
        self.animating = False
        self._set_draw_enabled(True)

    # ------------------------------------------------------------ build --
    def _build_header(self):
        W, px = self.W, self.px
        c = tk.Canvas(self.root, width=px(W), height=px(104), bg=RED, highlightthickness=0)
        c.pack(fill="x")
        c.create_rectangle(0, px(94), px(W), px(104), fill=YELLOW, width=0)
        c.create_text(px(30), px(44), anchor="w", text="LOTEK", fill=YELLOW, font=self.f(50, "bold"))
        c.create_text(px(32), px(78), anchor="w", text="losowarka szczęśliwych liczb",
                      fill="white", font=self.f(16))
        deco = [(7, YELLOW), (13, BLUE_BALL), (21, GREEN), (36, ORANGE), (49, "#F2F2F2")]
        for i, (n, col) in enumerate(deco):
            c.create_image(px(W - 262 + i * 52), px(46 + (7 if i % 2 else -3)),
                           image=self.art.ball(n, col, px(48)))

    def _build_presets(self):
        px = self.px
        fr = tk.Frame(self.root, bg=BG)
        fr.pack(fill="x", padx=px(20), pady=(px(16), px(4)))
        for i, g in enumerate(GAMES):
            t = tk.Label(fr, text=f"{g['name']}\n{g['sub']}", font=self.f(14, "bold"),
                         bg="white", fg=BLUE, padx=px(6), pady=px(9), cursor="hand2",
                         highlightthickness=2, highlightbackground=BLUE, bd=0)
            t.grid(row=i // 4, column=i % 4, padx=px(5), pady=px(5), sticky="nsew")
            t.bind("<Button-1>", lambda e, g=g: self.select_game(g))
            t.bind("<Enter>", lambda e, g=g: self._tile_hover(g, True))
            t.bind("<Leave>", lambda e, g=g: self._tile_hover(g, False))
            self.tiles[g["key"]] = t
        for col in range(4):
            fr.columnconfigure(col, weight=1, uniform="tiles")

    def _tile_hover(self, g, inside):
        if self.game is g:
            return
        self.tiles[g["key"]].configure(bg="#E6EEFC" if inside else "white")

    def _build_options(self):
        px = self.px
        self.opt = tk.Frame(self.root, bg=BG, height=px(58))
        self.opt.pack(fill="x", padx=px(25), pady=(px(6), 0))
        self.opt.pack_propagate(False)

    def _build_draw_button(self):
        px = self.px
        self.btn = tk.Label(self.root, text="LOSUJ!", font=self.f(30, "bold"), bg=RED, fg=YELLOW,
                            padx=px(56), pady=px(6), cursor="hand2",
                            highlightthickness=3, highlightbackground=YELLOW)
        self.btn.pack(pady=(px(4), px(14)))
        self.btn.bind("<Button-1>", lambda e: self.on_draw())
        self.btn.bind("<Enter>", lambda e: self.animating or self.btn.configure(bg=RED_DARK))
        self.btn.bind("<Leave>", lambda e: self.animating or self.btn.configure(bg=RED))

    def _set_draw_enabled(self, on):
        if on:
            self.btn.configure(bg=RED, fg=YELLOW, cursor="hand2")
        else:
            self.btn.configure(bg="#C9B9B9", fg="white", cursor="watch")

    def _build_result(self):
        px = self.px
        self.cw = px(self.W - 40)
        self.cv = tk.Canvas(self.root, width=self.cw, height=px(170), bg=CARD,
                            highlightthickness=2, highlightbackground="#E9D8A6")
        self.cv.pack(padx=px(20))

    def _build_footer(self):
        px = self.px
        fr = tk.Frame(self.root, bg=BG)
        fr.pack(fill="x", padx=px(20), pady=(px(10), px(16)))
        self.copy_btn = tk.Label(fr, text="Kopiuj wynik", font=self.f(14, "bold"),
                                 bg="white", fg=MUTED, padx=px(14), pady=px(6),
                                 highlightthickness=2, highlightbackground="#D8D0BC")
        self.copy_btn.pack(side="left")
        self.copy_btn.bind("<Button-1>", lambda e: self.copy_result())
        self._build_logo(fr)
        self.status = tk.Label(fr, text="", font=self.f(14), bg=BG, fg=MUTED, anchor="w")
        self.status.pack(side="left", padx=px(14), fill="x", expand=True)

    def _build_logo(self, parent):
        """Logo created.png w prawym dolnym rogu; klik otwiera stronę autora."""
        path = resource_path("created.png")
        if not path:
            return
        try:
            img = Image.open(path).convert("RGBA")
            max_w, max_h = self.px(200), self.px(44)
            k = min(max_w / img.width, max_h / img.height)
            if k < 1:
                img = img.resize((max(1, int(img.width * k)), max(1, int(img.height * k))), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, "PNG")
            self._logo = tk.PhotoImage(data=base64.b64encode(buf.getvalue()))
        except Exception:
            return
        lbl = tk.Label(parent, image=self._logo, bg=BG, cursor="hand2", bd=0)
        lbl.pack(side="right")
        lbl.bind("<Button-1>", lambda e: webbrowser.open(AUTHOR_URL))

    # ---------------------------------------------------------- options --
    def select_game(self, g):
        self.cancel_animation()
        if self.game is not None:
            self.tiles[self.game["key"]].configure(bg="white", fg=BLUE)
        self.game = g
        self.tiles[g["key"]].configure(bg=BLUE, fg="white")
        self.result = None
        self._set_copy_enabled(False)
        self.set_status("")
        self._fill_options()
        self._show_placeholder()

    def _fill_options(self):
        for w in self.opt.winfo_children():
            w.destroy()
        g, px = self.game, self.px
        row = tk.Frame(self.opt, bg=BG)
        row.pack(anchor="center", expand=True)

        def text(t, bold=False, color=DARK):
            tk.Label(row, text=t, font=self.f(17, "bold" if bold else "normal"),
                     bg=BG, fg=color).pack(side="left")

        if g.get("custom"):
            vcmd = (self.root.register(lambda P: P == "" or (P.isdigit() and len(P) <= 4)), "%P")
            for lbl, var in (("Od", self.c_from), ("Do", self.c_to), ("Ile liczb", self.c_count)):
                text(lbl + ":", bold=True, color=BLUE)
                e = tk.Entry(row, textvariable=var, width=6, justify="center", font=self.f(18, "bold"),
                             validate="key", validatecommand=vcmd, relief="flat",
                             highlightthickness=2, highlightbackground=BLUE, highlightcolor=RED)
                e.pack(side="left", padx=(px(6), px(22)), ipady=px(3))
                e.bind("<FocusIn>", lambda ev: ev.widget.select_range(0, "end"))
        elif g.get("choose"):
            text("Ile liczb:", bold=True, color=BLUE)
            sp = tk.Spinbox(row, from_=1, to=10, textvariable=self.choose_vars[g["key"]], width=3,
                            state="readonly", justify="center", font=self.f(18, "bold"),
                            readonlybackground="white", relief="flat",
                            highlightthickness=2, highlightbackground=BLUE, wrap=False)
            sp.pack(side="left", padx=(px(8), px(12)), ipady=px(2))
            sp.bind("<MouseWheel>", lambda ev: sp.invoke("buttonup" if ev.delta > 0 else "buttondown"))
            sp.bind("<Button-4>", lambda ev: sp.invoke("buttonup"))
            sp.bind("<Button-5>", lambda ev: sp.invoke("buttondown"))
            text(f"z zakresu {g['lo']}–{g['hi']}")
        else:
            text("Losuję ")
            text(f"{g['count']} liczb", bold=True, color=BLUE)
            text(f" z zakresu {g['lo']}–{g['hi']}")
            if "extra" in g:
                ex = g["extra"]
                n = ex["count"]
                text("  +  ")
                text(f"{n} {'liczbę' if n == 1 else 'liczby'}", bold=True, color=BLUE_BALL)
                text(f" z {ex['lo']}–{ex['hi']}")

    def _params(self):
        """Zwraca (lo, hi, count, extra|None) albo None (błąd w statusie)."""
        g = self.game
        if g.get("custom"):
            try:
                lo, hi, k = int(self.c_from.get()), int(self.c_to.get()), int(self.c_count.get())
            except ValueError:
                return self.error("Uzupełnij wszystkie pola: Od, Do i Ile liczb.")
            if lo > hi:
                return self.error("„Od” nie może być większe niż „Do”.")
            if hi > MAX_CUSTOM_VALUE:
                return self.error(f"Maksymalna wartość „Do” to {MAX_CUSTOM_VALUE}.")
            if k < 1:
                return self.error("Trzeba wylosować co najmniej 1 liczbę.")
            if k > MAX_CUSTOM_COUNT:
                return self.error(f"Naraz mogę wylosować maksymalnie {MAX_CUSTOM_COUNT} liczb.")
            size = hi - lo + 1
            if k > size:
                return self.error(f"W zakresie {lo}–{hi} jest tylko {size} liczb – "
                                  f"nie wylosuję {k} bez powtórzeń.")
            return lo, hi, k, None
        k = self.choose_vars[g["key"]].get() if g.get("choose") else g["count"]
        return g["lo"], g["hi"], k, g.get("extra")

    # ------------------------------------------------------------- draw --
    def on_draw(self):
        if self.animating:
            return
        p = self._params()
        if not p:
            return
        lo, hi, k, ex = p
        main = draw_numbers(lo, hi, k)
        extra = draw_numbers(ex["lo"], ex["hi"], ex["count"]) if ex else []
        self.result = (main, extra)
        self.set_status("Losuję…")
        self._set_copy_enabled(False)
        self._animate(main, (lo, hi), extra, (ex["lo"], ex["hi"]) if ex else None,
                      ex["label"] if ex else None)

    def _layout(self, sections):
        """sections: [(label, n)] -> (slots per sekcja, label pos, wysokość)."""
        px, Wc = self.px, self.cw
        pad, label_h = px(18), px(26)
        y = pad
        out = []
        for label, n in sections:
            d, gap = (px(60), px(11)) if n <= 10 else (px(48), px(9)) if n <= 24 else (px(40), px(8))
            per = max(1, (Wc - 2 * pad + gap) // (d + gap))
            rows = math.ceil(n / per)
            label_y = y
            y += label_h
            slots = []
            for i in range(n):
                r, c = divmod(i, per)
                in_row = min(per, n - r * per)
                x0 = (Wc - (in_row * d + (in_row - 1) * gap)) / 2
                slots.append((x0 + c * (d + gap) + d / 2, y + r * (d + gap) + d / 2, d))
            y += rows * d + (rows - 1) * gap + px(18)
            out.append((label, label_y, slots))
        return out, y + pad - px(10)

    def _paint_background(self, h):
        cv, step = self.cv, self.px(22)
        cv.delete("all")
        cv.configure(height=h)
        for x in range(step, self.cw, step):
            cv.create_line(x, 0, x, h + 10, fill=GRID)
        for y in range(step, h + 10, step):
            cv.create_line(0, y, self.cw, y, fill=GRID)

    def _show_placeholder(self):
        h = self.px(170)
        self._paint_background(h)
        self.cv.create_text(self.cw / 2, h / 2 - self.px(12), text="Kliknij  LOSUJ!",
                            font=self.f(26, "bold"), fill="#C9BFA4")
        self.cv.create_text(self.cw / 2, h / 2 + self.px(22), text="(albo naciśnij Enter)",
                            font=self.f(15), fill="#C9BFA4")

    DROP_MS = 620      # czas spadania jednej kuli
    SHADOW_LEVELS = 8

    def _animate(self, main, main_rng, extra, extra_rng, extra_label):
        self.cancel_animation()
        self.animating = True
        self._set_draw_enabled(False)

        sections = [("Twoje liczby", len(main))]
        if extra:
            sections.append((extra_label, len(extra)))
        layout, h = self._layout(sections)
        self._paint_background(h)

        data = [(main, YELLOW)] + ([(extra, BLUE_BALL)] if extra else [])
        balls = []
        for (label, ly, slots), (nums, color) in zip(layout, data):
            self.cv.create_text(self.px(20), ly + self.px(4), anchor="nw", text=label.upper(),
                                font=self.f(14, "bold"), fill=BLUE if color == YELLOW else BLUE_BALL)
            for (cx, cy, d), n in zip(slots, nums):
                balls.append((cx, cy, int(d), n, color))

        # przygotuj grafiki zanim ruszy animacja (płynność)
        for cx, cy, d, n, color in balls:
            self.art.ball(n, color, d)
            for lv in range(1, self.SHADOW_LEVELS + 1):
                self.art.shadow(d, lv, self.SHADOW_LEVELS)

        stagger = min(150, 1700 / max(1, len(balls)))
        self.anim = []
        for i, (cx, cy, d, n, color) in enumerate(balls):
            sy = cy + d * 0.46
            sh = self.cv.create_image(cx, sy, image=self.art.shadow(d, 1, self.SHADOW_LEVELS),
                                      state="hidden")
            y0 = -d * 0.6
            ball = self.cv.create_image(cx, y0, image=self.art.ball(n, color, d), state="hidden")
            self.anim.append(dict(ball=ball, sh=sh, d=d, x=cx, y0=y0, y1=cy,
                                  start=i * stagger, shown=False, done=False, lv=1))
        self.t0 = time.perf_counter()
        self._tick()

    def _tick(self):
        t = (time.perf_counter() - self.t0) * 1000
        cv, L = self.cv, self.SHADOW_LEVELS
        finished = True
        for b in self.anim:
            if b["done"]:
                continue
            p = (t - b["start"]) / self.DROP_MS
            if p <= 0:
                finished = False
                continue
            if not b["shown"]:
                cv.itemconfigure(b["ball"], state="normal")
                cv.itemconfigure(b["sh"], state="normal")
                b["shown"] = True
            if p >= 1:
                cv.coords(b["ball"], b["x"], b["y1"])
                cv.itemconfigure(b["sh"], image=self.art.shadow(b["d"], L, L))
                b["done"] = True
                continue
            finished = False
            y = b["y0"] + (b["y1"] - b["y0"]) * ease_out_bounce(p)
            cv.coords(b["ball"], b["x"], y)
            # cień ciemnieje i rośnie, im kula bliżej "stołu"
            closeness = 1 - min(1.0, (b["y1"] - y) / max(1.0, b["y1"] - b["y0"]))
            lv = max(1, min(L, 1 + int(closeness * (L - 1) + 0.5)))
            if lv != b["lv"]:
                cv.itemconfigure(b["sh"], image=self.art.shadow(b["d"], lv, L))
                b["lv"] = lv
        if finished:
            self.anim_job = None
            self._finish()
        else:
            self.anim_job = self.root.after(15, self._tick)

    def _finish(self):
        self.anim = []
        self.animating = False
        self._set_draw_enabled(True)
        self._set_copy_enabled(True)
        main, extra = self.result
        msg = f"Gotowe – {liczb(len(main))}"
        if extra:
            msg += f" + {len(extra)} {'dodatkowa' if len(extra) == 1 else 'dodatkowe'}"
        self.set_status(msg + ". Powodzenia!")

    # ------------------------------------------------------------- misc --
    def result_text(self):
        main, extra = self.result
        t = ", ".join(map(str, main))
        return t + ("  +  " + ", ".join(map(str, extra)) if extra else "")

    def copy_result(self):
        if not self.result or self.animating:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.result_text())
        self.root.update()
        self.set_status(f"Skopiowano: {self.result_text()}", color=GREEN)

    def _set_copy_enabled(self, on):
        self.copy_btn.configure(fg=BLUE if on else MUTED, cursor="hand2" if on else "arrow",
                                highlightbackground=BLUE if on else "#D8D0BC")

    def set_status(self, text, color=MUTED):
        self.status.configure(text=text, fg=color)

    def error(self, text):
        self.set_status(text, color=RED)
        return None


def main():
    try:  # ostre czcionki na ekranach z skalowaniem (Windows)
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    LotekApp(root)
    root.update_idletasks()
    w, h = root.winfo_width(), root.winfo_height()
    x = (root.winfo_screenwidth() - w) // 2
    y = max(0, (root.winfo_screenheight() - h) // 3)
    root.geometry(f"+{x}+{y}")
    root.mainloop()


ICON_PNG = (
    "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"
)

if __name__ == "__main__":
    main()
