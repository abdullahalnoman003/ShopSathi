"""Generic node-and-edge diagrams (architecture, state, use case, ER) on top of dgkit. All black and white."""
import textwrap

from dgkit import FS, LW, Canvas, chars_for


class Graph:
    def __init__(self, name, w, h, fs=FS):
        self.c = Canvas(w, h, name)
        self.fs = fs
        self.n = {}

    # node kinds: box, round (state), ellipse (use case), cyl, actor, diamond, text, start, end
    def node(self, key, x, y, w, h, text="", kind="box", dashed=False, bold=False, fs=None, double=False):
        """x, y = centre of the node."""
        fs = fs or self.fs
        c = self.c
        if kind == "box":
            c.box(x - w / 2, y - h / 2, w, h, text, fs=fs, bold=bold, dashed=dashed, rounded=False, double=double)
        elif kind == "round":
            c.box(x - w / 2, y - h / 2, w, h, text, fs=fs, bold=bold, dashed=dashed)
        elif kind == "ellipse":
            c.ellipse(x, y, w, h, text, fs=fs, dashed=dashed)
        elif kind == "cyl":
            c.cylinder(x - w / 2, y - h / 2, w, h, text, fs=fs)
        elif kind == "diamond":
            c.diamond(x, y, w, h, text, fs=fs)
        elif kind == "start":
            import matplotlib.patches as mp

            c.ax.add_patch(mp.Circle((x, y), 2.8, fc="black", ec="black", zorder=3))
            w = h = 5.6
        elif kind == "end":
            import matplotlib.patches as mp

            c.ax.add_patch(mp.Circle((x, y), 3.4, fc="white", ec="black", lw=LW, zorder=3))
            c.ax.add_patch(mp.Circle((x, y), 2.0, fc="black", ec="black", zorder=4))
            w = h = 6.8
        elif kind == "actor":
            c.actor(x, y - h / 2 + 2.2, text, fs=fs)
            w, h = 12, h
        self.n[key] = (x, y, w, h)

    def pt(self, key, side, off=0.0):
        x, y, w, h = self.n[key]
        return {"l": (x - w / 2, y + off), "r": (x + w / 2, y + off), "t": (x + off, y - h / 2), "b": (x + off, y + h / 2)}[side]

    def edge(self, a, b, sa="r", sb="l", label=None, dashed=False, arrow="end", via=None, oa=0.0, ob=0.0, label_at=0.5, fs=None):
        """via: list of intermediate points. Without via, a straight line or one elbow is drawn automatically."""
        p1, p2 = self.pt(a, sa, oa), self.pt(b, sb, ob)
        pts = [p1] + (via or []) + [p2]
        if not via and abs(p1[0] - p2[0]) > 0.5 and abs(p1[1] - p2[1]) > 0.5:
            if sa in "lr" and sb in "tb":
                pts = [p1, (p2[0], p1[1]), p2]
            elif sa in "tb" and sb in "lr":
                pts = [p1, (p1[0], p2[1]), p2]
            elif sa in "lr":
                mx = (p1[0] + p2[0]) / 2
                pts = [p1, (mx, p1[1]), (mx, p2[1]), p2]
            else:
                my = (p1[1] + p2[1]) / 2
                pts = [p1, (p1[0], my), (p2[0], my), p2]
        self.c.line(pts, dashed=dashed, arrow=arrow, label=label, label_at=label_at, fs=fs or self.fs - 0.6)

    def line(self, pts, **kw):
        self.c.line(pts, **kw)

    def group(self, x, y, w, h, title, dashed=False):
        self.c.titled(x, y, w, h, title, fs=self.fs, dashed=dashed)

    def text(self, x, y, s, **kw):
        self.c.text(x, y, s, **kw)

    def save(self):
        return self.c.save()


def table_box(c, x, y, w, title, rows, fs=5.8, row_h=3.7, title_h=5.2, pk=()):
    """ER entity: title strip and one line per column. Returns (x, y, w, h)."""
    h = title_h + row_h * len(rows) + 1.2
    c.ax.add_patch(__import__("matplotlib").patches.Rectangle((x, y), w, h, fc="white", ec="black", lw=LW, zorder=2))
    c.ax.add_patch(__import__("matplotlib").patches.Rectangle((x, y), w, title_h, fc="white", ec="black", lw=LW, zorder=2))
    c.text(x + w / 2, y + title_h / 2 + 0.2, title, fs + 0.6, bold=True)
    for i, r in enumerate(rows):
        c.text(x + 1.5, y + title_h + row_h * (i + 0.6) + 0.5, r, fs, ha="left", bold=r.startswith("PK"))
    return (x, y, w, h)
