"""Black-and-white diagram toolkit (matplotlib). One unit = 1 mm of the printed figure at full width, so a font size of 7.5 pt
is 7.5 pt on paper when the canvas is about 150 to 170 units wide."""

import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, FancyBboxPatch, Polygon, Rectangle

OUT = Path(__file__).resolve().parent / "figures"
OUT.mkdir(exist_ok=True)
plt.rcParams["font.family"] = "Arial"
plt.rcParams["text.color"] = "black"
LW = 0.9
FS = 7.0
MM_PER_PT = 0.3528


def chars_for(width, fs):
    return max(4, int((width - 2.0) / (fs * 0.5 * MM_PER_PT)))


class Canvas:
    def __init__(self, w, h, name, dpi=220):
        self.w, self.h, self.name, self.dpi = w, h, name, dpi
        self.fig = plt.figure(figsize=(w / 25.4, h / 25.4), dpi=dpi, facecolor="white")
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, w)
        self.ax.set_ylim(h, 0)  # y grows downwards, like a drawing
        self.ax.axis("off")
        self.ax.set_aspect("equal")

    # ---------------------------------------------------------------- text
    def text(self, x, y, s, fs=FS, bold=False, italic=False, ha="center", va="center", wrap=None, mono=False, lh=1.18):
        if wrap:
            s = "\n".join(textwrap.fill(line, wrap) for line in s.split("\n"))
        self.ax.text(x, y, s, fontsize=fs, ha=ha, va=va, fontweight="bold" if bold else "normal", style="italic" if italic else "normal",
                     family="Courier New" if mono else "Arial", linespacing=lh, color="black", zorder=6)

    def _label(self, x, y, s, fs=FS - 0.5):
        self.ax.text(x, y, s, fontsize=fs, ha="center", va="center", color="black", zorder=7, family="Arial",
                     bbox=dict(facecolor="white", edgecolor="none", pad=0.6), linespacing=1.1)

    # ---------------------------------------------------------------- shapes (x, y = top-left corner)
    def box(self, x, y, w, h, s="", fs=FS, bold=False, dashed=False, rounded=True, lw=LW, align="center", wrap=True, double=False, fill="white", mono=False):
        patch = (FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.6", fc=fill, ec="black", lw=lw, ls="--" if dashed else "-", zorder=2)
                 if rounded else Rectangle((x, y), w, h, fc=fill, ec="black", lw=lw, ls="--" if dashed else "-", zorder=2))
        self.ax.add_patch(patch)
        if double:
            self.ax.add_patch(Rectangle((x + 1.2, y + 1.2), w - 2.4, h - 2.4, fc="none", ec="black", lw=lw * 0.7, zorder=2))
        if s:
            body = "\n".join(textwrap.fill(line, chars_for(w, fs)) for line in s.split("\n")) if wrap else s
            if align == "center":
                self.text(x + w / 2, y + h / 2, body, fs, bold, mono=mono)
            else:
                self.text(x + 2, y + h / 2, body, fs, bold, ha="left", mono=mono)
        return (x, y, w, h)

    def titled(self, x, y, w, h, title, fs=FS, dashed=False, fill="white", title_h=6.0):
        """A container with a title strip (package / layer / node)."""
        self.ax.add_patch(Rectangle((x, y), w, h, fc=fill, ec="black", lw=LW, ls="--" if dashed else "-", zorder=1))
        self.text(x + 2, y + title_h / 2 + 0.3, title, fs, bold=True, ha="left")
        self.ax.plot([x, x + w], [y + title_h, y + title_h], color="black", lw=0.5, zorder=1)

    def ellipse(self, cx, cy, w, h, s="", fs=FS, dashed=False, lw=LW):
        self.ax.add_patch(Ellipse((cx, cy), w, h, fc="white", ec="black", lw=lw, ls="--" if dashed else "-", zorder=2))
        if s:
            self.text(cx, cy, "\n".join(textwrap.fill(line, chars_for(w * 0.82, fs)) for line in s.split("\n")), fs)

    def diamond(self, cx, cy, w, h, s="", fs=FS - 0.5):
        self.ax.add_patch(Polygon([(cx, cy - h / 2), (cx + w / 2, cy), (cx, cy + h / 2), (cx - w / 2, cy)], closed=True, fc="white", ec="black", lw=LW, zorder=2))
        if s:
            self.text(cx, cy, "\n".join(textwrap.fill(line, chars_for(w * 0.62, fs)) for line in s.split("\n")), fs)

    def cylinder(self, x, y, w, h, s="", fs=FS):
        import numpy as np

        e = min(h * 0.22, 7)
        t = np.linspace(0, np.pi, 40)
        self.ax.add_patch(Rectangle((x, y + e / 2), w, h - e, fc="white", ec="none", zorder=2))
        self.ax.plot([x, x], [y + e / 2, y + h - e / 2], color="black", lw=LW, zorder=3)
        self.ax.plot([x + w, x + w], [y + e / 2, y + h - e / 2], color="black", lw=LW, zorder=3)
        self.ax.plot(x + w / 2 + (w / 2) * np.cos(t), y + h - e / 2 + (e / 2) * np.sin(t), color="black", lw=LW, zorder=3)
        self.ax.add_patch(Ellipse((x + w / 2, y + e / 2), w, e, fc="white", ec="black", lw=LW, zorder=3))
        self.text(x + w / 2, y + h / 2 + e / 2, "\n".join(textwrap.fill(l, chars_for(w, fs)) for l in s.split("\n")), fs)

    def actor(self, cx, cy, label, fs=FS, scale=1.0):
        r = 2.2 * scale
        self.ax.add_patch(matplotlib.patches.Circle((cx, cy), r, fc="white", ec="black", lw=LW, zorder=3))
        k = scale
        self.ax.plot([cx, cx], [cy + r, cy + r + 7 * k], color="black", lw=LW, zorder=3)
        self.ax.plot([cx - 4 * k, cx + 4 * k], [cy + r + 2.5 * k, cy + r + 2.5 * k], color="black", lw=LW, zorder=3)
        self.ax.plot([cx, cx - 3.5 * k], [cy + r + 7 * k, cy + r + 13 * k], color="black", lw=LW, zorder=3)
        self.ax.plot([cx, cx + 3.5 * k], [cy + r + 7 * k, cy + r + 13 * k], color="black", lw=LW, zorder=3)
        self.text(cx, cy + r + 13 * k + 4, label, fs, bold=True)

    # ---------------------------------------------------------------- lines
    def line(self, pts, dashed=False, lw=LW, arrow=None, label=None, label_at=0.5, fs=FS - 0.5, dot=False):
        """pts: [(x, y), ...]. arrow: None | 'end' | 'both' | 'open' (open triangle, for inheritance/include)."""
        xs, ys = zip(*pts)
        self.ax.plot(xs, ys, color="black", lw=lw, ls="--" if dashed else "-", zorder=1.5, solid_capstyle="butt")
        if arrow in ("end", "both", "open"):
            self._head(pts[-2], pts[-1], open_=(arrow == "open"))
        if arrow == "both":
            self._head(pts[1], pts[0])
        if dot:
            self.ax.plot([pts[0][0]], [pts[0][1]], marker="o", ms=3, color="black", zorder=3)
        if label:
            # the label sits on the longest segment
            segs = list(zip(pts[:-1], pts[1:]))
            a, b = max(segs, key=lambda s: (s[0][0] - s[1][0]) ** 2 + (s[0][1] - s[1][1]) ** 2)
            mx, my = a[0] + (b[0] - a[0]) * label_at, a[1] + (b[1] - a[1]) * label_at
            if abs(b[0] - a[0]) < 0.01:  # vertical: the label goes to the right of the line
                self.ax.text(mx + 1.5, my, label, fontsize=fs, ha="left", va="center", zorder=7, family="Arial")
            else:  # horizontal or sloped: just above the line
                self.ax.text(mx, my - 1.0, label, fontsize=fs, ha="center", va="bottom", zorder=7, family="Arial",
                             bbox=dict(facecolor="white", edgecolor="none", pad=0.3))

    def _head(self, a, b, open_=False, size=1.7):
        import math

        dx, dy = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dy) or 1
        ux, uy = dx / d, dy / d
        px, py = -uy, ux
        p1 = (b[0] - ux * size * 1.7 + px * size * 0.7, b[1] - uy * size * 1.7 + py * size * 0.7)
        p2 = (b[0] - ux * size * 1.7 - px * size * 0.7, b[1] - uy * size * 1.7 - py * size * 0.7)
        self.ax.add_patch(Polygon([b, p1, p2], closed=True, fc="white" if open_ else "black", ec="black", lw=0.7, zorder=4))

    # ---------------------------------------------------------------- finish
    def save(self):
        path = OUT / f"{self.name}.png"
        self.fig.savefig(path, dpi=self.dpi, facecolor="white")
        plt.close(self.fig)
        return path


# --------------------------------------------------------------------------------------------- composite diagrams


def sequence(name, participants, messages, width=170, fs=6.6, row=8.6, top=4, col_w=None, notes=None, title=None):
    """participants: [str]; messages: [(from_idx, to_idx, label, kind)] kind: 'call' | 'return' | 'self' | 'async' | 'note:<text>'.
    A message may also be ('group', 'text') for a divider band."""
    n = len(participants)
    margin = 4
    col_w = col_w or (width - 2 * margin) / n
    xs = [margin + col_w * (i + 0.5) for i in range(n)]
    head_h = 11
    total_rows = sum(2.0 if (m[0] == "group") else (1.4 if m[3] == "self" else 1.0) for m in messages)
    height = top + head_h + total_rows * row + 8
    c = Canvas(width, height, name)
    for i, p in enumerate(participants):
        c.box(xs[i] - col_w / 2 + 1.5, top, col_w - 3, head_h, p, fs=fs, bold=True, rounded=False)
        c.line([(xs[i], top + head_h), (xs[i], height - 3)], dashed=True, lw=0.6)
    y = top + head_h + row * 0.7
    for m in messages:
        if m[0] == "group":
            c.ax.add_patch(Rectangle((margin, y - row * 0.55), width - 2 * margin, row * 1.1, fc="white", ec="black", lw=0.6, ls=":", zorder=1.2))
            c.text(margin + 2, y, m[1], fs - 0.4, italic=True, bold=True, ha="left")
            y += row * 2.0
            continue
        a, b, label, kind = m
        if kind == "self":
            x = xs[a]
            c.line([(x, y), (x + 9, y), (x + 9, y + row * 0.9), (x, y + row * 0.9)], arrow="end")
            c.text(x + 11, y + row * 0.45, label, fs - 0.5, ha="left")
            y += row * 1.4
        else:
            dashed = kind == "return"
            x1, x2 = xs[a], xs[b]
            off = 0.0
            c.line([(x1, y), (x2, y)], dashed=dashed, arrow="end" if kind != "async" else "end")
            mid = (x1 + x2) / 2
            c.ax.text(mid, y - 1.7, label, fontsize=fs - 0.5, ha="center", va="bottom", zorder=7,
                      bbox=dict(facecolor="white", edgecolor="none", pad=0.4), linespacing=1.1, family="Arial")
            y += row
    return c


def hbar_chart(name, labels, values, title, xlabel, width=150, height=70, hatches=None, unit="s", limit=None, limit_label=None, fmt="{:.1f}"):
    fig, ax = plt.subplots(figsize=(width / 25.4, height / 25.4), dpi=220)
    ys = range(len(labels))
    hs = hatches or ["", "///", "\\\\\\", "xxx", "..."]
    bars = ax.barh(list(ys), values, color="white", edgecolor="black", linewidth=0.9, height=0.55)
    for b, h in zip(bars, hs * 5):
        b.set_hatch(h)
    ax.set_yticks(list(ys))
    ax.set_yticklabels(labels, fontsize=7)
    ax.invert_yaxis()
    ax.set_xlabel(xlabel, fontsize=7.5)
    ax.tick_params(axis="x", labelsize=7)
    for b, v in zip(bars, values):
        ax.text(v + max(values) * 0.01, b.get_y() + b.get_height() / 2, fmt.format(v) + (" " + unit if unit else ""), va="center", fontsize=7)
    if limit is not None:
        ax.axvline(limit, color="black", ls="--", lw=1)
        ax.text(limit, -0.62, limit_label or f"target {limit} {unit}", fontsize=7, ha="center", va="bottom")
    ax.set_xlim(0, max(max(values), limit or 0) * 1.22)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_title(title, fontsize=8, fontweight="bold", pad=14 if limit is not None else 6)
    fig.tight_layout()
    path = OUT / f"{name}.png"
    fig.savefig(path, dpi=220, facecolor="white")
    plt.close(fig)
    return path
