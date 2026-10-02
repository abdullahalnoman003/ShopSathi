"""Activity and state diagrams (black and white), built on dgkit."""

import textwrap

import matplotlib
from matplotlib.patches import Rectangle

from dgkit import FS, LW, MM_PER_PT, Canvas, chars_for


def activity(name, steps, width=170, main_x=48, side_x=128, bw=76, sw=70, fs=6.8, gap=6.5):
    """steps: ('start',) | ('act', text) | ('dec', question, opts) | ('end',).
    opts = {'branch': [steps], 'side': 'no'|'yes', 'rejoin': bool, 'side_label': 'no', 'main_label': 'yes'}.
    The main flow runs down the left column. The side branch of a decision runs down the right column and either joins the
    main flow again (rejoin) or ends in its own end node."""
    nodes, edges = [], []

    def lines_of(text, w):
        return sum(len(textwrap.wrap(line, chars_for(w, fs))) or 1 for line in text.split("\n"))

    def act_h(text, w):
        return max(8.5, 3.6 + lines_of(text, w) * fs * 1.22 * MM_PER_PT)

    def place(items, x, w, y, entry=None):
        prev, prev_label, rejoin = None, None, None
        for it in items:
            kind = it[0]
            if kind == "start":
                nw, nh = 6, 6
            elif kind == "end":
                nw, nh = 7, 7
            elif kind == "act":
                nw, nh = w, act_h(it[1], w)
            else:
                nw, nh = min(w, 58), max(18, 8 + lines_of(it[1], 40) * fs * 1.2 * MM_PER_PT)
            ty = entry[1] - nh / 2 if (prev is None and entry is not None) else y
            node = dict(kind=kind, x=x, y=ty, w=nw, h=nh, text=it[1] if len(it) > 1 else "")
            nodes.append(node)
            if prev is not None:
                edges.append(dict(pts=[(x, prev["y"] + prev["h"]), (x, ty)], label=prev_label))
            elif entry is not None:
                fx, fy, lab = entry
                tx = x - nw / 2 if fx < x else x + nw / 2
                edges.append(dict(pts=[(fx, fy), (tx, fy)], label=lab))
            if rejoin is not None:
                bx, by = rejoin
                mid = ty + nh / 2
                edges.append(dict(pts=[(bx, by), (bx, mid), (x + (nw / 2 if bx > x else -nw / 2), mid)], label=None))
                rejoin = None
            y = ty + nh + gap
            prev_label = None
            if kind == "dec":
                opts = it[2]
                side = opts.get("side", "no")
                sdir = 1 if x < width / 2 else -1
                bx = side_x if sdir > 0 else main_x
                from_pt = (x + nw / 2 * sdir, ty + nh / 2, opts.get("side_label", side))
                sub_bottom, sub_last = place(opts["branch"], bx, sw, ty, entry=from_pt)
                prev_label = opts.get("main_label", "yes" if side == "no" else "no")
                if opts.get("rejoin", False) and sub_last["kind"] != "end":
                    rejoin = (bx, sub_last["y"] + sub_last["h"])
                y = max(y, sub_bottom + gap)
            prev = node
        # a branch that has to join the flow below: the caller connects it to the next node
        place.pending = rejoin
        return (prev["y"] + prev["h"] if prev else y), prev

    # the rejoin of a branch is drawn when the next main node is placed: handled by wrapping `place` for the main column
    main_nodes_before = 0
    bottom, last = place(steps, main_x, bw, 4)
    height = max(n["y"] + n["h"] for n in nodes) + 6
    c = Canvas(width, height, name)
    for n in nodes:
        k = n["kind"]
        if k == "start":
            c.ax.add_patch(matplotlib.patches.Circle((n["x"], n["y"] + 3), 3, fc="black", ec="black", zorder=3))
        elif k == "end":
            c.ax.add_patch(matplotlib.patches.Circle((n["x"], n["y"] + 3.5), 3.5, fc="white", ec="black", lw=LW, zorder=3))
            c.ax.add_patch(matplotlib.patches.Circle((n["x"], n["y"] + 3.5), 2.0, fc="black", ec="black", zorder=4))
        elif k == "act":
            c.box(n["x"] - n["w"] / 2, n["y"], n["w"], n["h"], n["text"], fs=fs)
        else:
            c.diamond(n["x"], n["y"] + n["h"] / 2, n["w"], n["h"], n["text"], fs=fs - 0.4)
    for e in edges:
        c.line(e["pts"], arrow="end", label=e["label"], fs=fs - 0.7)
    return c
