"""Batch B: use case, state, ER and wireframe diagrams."""
import json
import math
from pathlib import Path

from dg2 import Graph, table_box
from dgkit import Canvas

INV = json.load(open(Path(__file__).parent / "data" / "inventory.json", encoding="utf8"))


# ------------------------------------------------------------------------------------------------ use case diagrams
def usecase(name, left, right, ucs, links, title, w=170, row_h=12.6, uc_w=74.0, uc_h=10.0):
    """One column of use cases inside the system box; actors left and right; each line ends on the side of its ellipse."""
    n = len(ucs)
    h = 16 + n * row_h + 4
    g = Graph(name, w, max(h, 14 + 36 * max(len(left), len(right))))
    bx, bw = 36, w - 72
    g.c.ax.add_patch(__import__("matplotlib").patches.Rectangle((bx, 3), bw, g.c.h - 6, fc="white", ec="black", lw=0.9, zorder=1))
    g.text(bx + bw / 2, 8, title, bold=True, fs=7.2)
    pos = {}
    for i, (k, t) in enumerate(ucs):
        x, y = w / 2, 16 + i * row_h + uc_h / 2
        g.node(k, x, y, uc_w, uc_h, t, "ellipse", fs=6.2)
        pos[k] = (x, y)
    ap = {}
    for side, actors in (("l", left), ("r", right)):
        m = len(actors)
        for i, (k, label) in enumerate(actors):
            cy = 6 + (g.c.h - 12) * (i + 0.5) / m
            cx = 17 if side == "l" else w - 17
            g.node(k, cx, cy, 12, 30, label, "actor", fs=6.4)
            ap[k] = (cx, cy - 14 + 2.2 + 2.5 + 2.2, side)
    for a, u in links:
        ax, ay, side = ap[a]
        ux, uy = pos[u]
        ex = ux - uc_w / 2 if side == "l" else ux + uc_w / 2
        g.line([(ax + (5 if side == "l" else -5), ay), (ex, uy)], lw=0.6)
    return g


def uc_seller_setup():
    ucs = [("u1", "UC-01 Sign up and create shop"), ("u2", "UC-02 Log in and log out"), ("u3", "UC-03 Reset password"),
           ("u4", "UC-04 Manage products"), ("u5", "UC-05 Upload or delete product photos"), ("u6", "UC-06 Import products from CSV"),
           ("u7", "UC-07 Set shop policy and delivery"), ("u8", "UC-08 Try the AI in Test Chat"), ("u9", "UC-09 Connect or disconnect Facebook Page"),
           ("u10", "UC-10 Add or remove moderators"), ("u11", "UC-11 View or change plan"), ("u12", "UC-12 Delete shop")]
    links = [("own", k) for k, _ in ucs] + [("fbk", "u9"), ("llm", "u8"), ("llm", "u4")]
    g = usecase("uc_setup", [("own", "Shop owner")], [("fbk", "Facebook"), ("llm", "OpenAI / Gemini")], ucs, links, "ShopSathi: shop setup and administration")
    return g.save()


def uc_daily():
    ucs = [("d1", "UC-13 View chat list and read chats"), ("d2", "UC-14 Reply to a customer"), ("d3", "UC-15 Pause or resume AI"),
           ("d4", "UC-16 Resolve a flagged chat"), ("d5", "UC-17 Review and edit draft orders"), ("d6", "UC-18 Confirm or cancel an order"),
           ("d7", "UC-19 Export confirmed orders (CSV)"), ("d8", "UC-20 See notifications"), ("d9", "UC-21 View reports"),
           ("d10", "UC-22 Read weekly AI summary")]
    links = [("own", k) for k, _ in ucs] + [("mod", k) for k, _ in ucs if k not in ("d9", "d10")] + [("fb", "d2")]
    g = usecase("uc_daily", [("own", "Shop owner"), ("mod", "Moderator")], [("fb", "Facebook")], ucs, links, "ShopSathi: daily shop work")
    return g.save()


def uc_customer():
    ucs = [("c1", "UC-23 Ask about product, price or stock"), ("c2", "UC-24 Ask about delivery and policy"), ("c3", "UC-25 Ask for suggestions with a budget"),
           ("c4", "UC-26 Give order details in chat"), ("c5", "UC-27 Ask for a human"), ("c6", "UC-28 Receive AI reply (24-hour window)"),
           ("c7", "UC-29 Detect complaint, refund or abuse"), ("c8", "UC-30 Create draft order")]
    links = [("cu", k) for k in ("c1", "c2", "c3", "c4", "c5", "c6")] + [("ai", k) for k in ("c1", "c2", "c3", "c4", "c6", "c7", "c8")] + [("fbk", "c6"), ("fbk", "c1")]
    g = usecase("uc_customer", [("cu", "Customer")], [("ai", "AI engine"), ("fbk", "Facebook\nMessenger")], ucs, links, "ShopSathi: customer chat on Messenger")
    return g.save()


def uc_admin():
    ucs = [("a1", "UC-31 Search and view shops"), ("a2", "UC-32 Suspend or reactivate a shop"), ("a3", "UC-33 Change a shop's plan"),
           ("a4", "UC-34 Edit plan limits and prices"), ("a5", "UC-35 View AI usage and cost"), ("a6", "UC-36 View system health"),
           ("a7", "UC-37 Create weekly insights (scheduled)"), ("a8", "UC-38 Log in as platform admin")]
    links = [("adm", k) for k in ("a1", "a2", "a3", "a4", "a5", "a6", "a8")] + [("tm", "a7")]
    g = usecase("uc_admin", [("adm", "Platform admin")], [("tm", "Scheduler\n(Celery beat)")], ucs, links, "ShopSathi: platform administration")
    return g.save()


# ------------------------------------------------------------------------------------------------ state diagrams
def state_order():
    g = Graph("st_order", 170, 62)
    g.node("s", 10, 31, 0, 0, "", "start")
    g.node("draft", 48, 31, 44, 20, "draft\n(created by the AI from chat\nor by the seller;\nthe seller can edit it)", "round", fs=6.2)
    g.node("conf", 144, 14, 40, 16, "confirmed\n(confirmed_at, confirmed_by)", "round", fs=6.2)
    g.node("canc", 144, 48, 40, 16, "cancelled\n(cancelled_at)", "round", fs=6.2)
    g.edge("s", "draft", "r", "l")
    g.edge("draft", "conf", "r", "l", None, via=[(86, 31), (86, 14)])
    g.edge("draft", "canc", "r", "l", None, via=[(86, 31), (86, 48)])
    g.text(103, 11, "seller confirms", fs=6.0)
    g.text(103, 45, "seller cancels", fs=6.0)
    g.text(104, 31, "Only a draft order can be\nconfirmed, cancelled or edited.\nOther states: HTTP 409.", fs=5.8)
    return g.save()


def state_chat():
    g = Graph("st_chat", 170, 84)
    g.node("s", 8, 18, 0, 0, "", "start")
    g.node("a", 44, 18, 44, 18, "AI active\nnot flagged", "round", fs=6.4)
    g.node("p", 126, 18, 44, 18, "AI paused\nnot flagged", "round", fs=6.4)
    g.node("af", 44, 64, 44, 18, "AI active\nflagged", "round", fs=6.4)
    g.node("pf", 126, 64, 44, 18, "AI paused\nflagged", "round", fs=6.4)
    g.edge("s", "a", "r", "l")
    g.edge("a", "p", "r", "l", "seller pauses AI", oa=-4, ob=-4)
    g.edge("p", "a", "l", "r", "seller resumes AI", oa=4, ob=4)
    g.edge("af", "pf", "r", "l", "seller pauses AI", oa=-4, ob=-4)
    g.edge("pf", "af", "l", "r", "seller resumes AI", oa=4, ob=4)
    g.edge("pf", "p", "t", "b", "resolve flag", oa=6, ob=6)
    g.edge("af", "a", "t", "b", "resolve flag", oa=-6, ob=-6)
    g.edge("a", "pf", "r", "t", None, via=[(70, 30), (100, 40), (118, 55)], oa=4)
    g.text(78, 41, "handover\ndetected", fs=5.8)
    return g.save()


def state_message():
    g = Graph("st_msg", 170, 76)
    g.node("s", 8, 20, 0, 0, "", "start")
    g.node("pend", 36, 20, 36, 18, "pending\n(saved, queued)", "round", fs=6.4)
    g.node("proc", 84, 20, 36, 18, "processing\n(lock, AI engine)", "round", fs=6.4)
    g.node("rep", 148, 8, 34, 14, "replied\n(sent_at set)", "round", fs=6.4)
    g.node("skip", 148, 32, 34, 14, "skipped\n(reason stored)", "round", fs=6.4)
    g.node("fail", 148, 56, 34, 14, "failed\n(error stored)", "round", fs=6.4)
    g.edge("s", "pend", "r", "l")
    g.edge("pend", "proc", "r", "l", "worker\nstarts")
    g.edge("proc", "rep", "r", "l", None, via=[(108, 20), (108, 8)])
    g.edge("proc", "skip", "r", "l", None, via=[(108, 20), (108, 32)])
    g.edge("proc", "fail", "r", "l", None, via=[(108, 20), (108, 56)])
    g.text(120, 5, "Facebook accepted", fs=5.8)
    g.text(120, 29, "not sent", fs=5.8)
    g.text(120, 53, "exception or\nsend error", fs=5.8)
    g.text(70, 52, "Skip reasons: shop suspended, AI paused, no Page,\noutside the 24-hour window, plan limit reached.", fs=5.8)
    return g.save()


def state_shop():
    g = Graph("st_shop", 170, 40)
    g.node("s", 10, 20, 0, 0, "", "start")
    g.node("act", 56, 20, 44, 16, "active", "round")
    g.node("sus", 130, 20, 44, 16, "suspended", "round")
    g.edge("s", "act", "r", "l", "signup")
    g.edge("act", "sus", "r", "l", "admin suspends", oa=-4, ob=-4)
    g.edge("sus", "act", "l", "r", "admin reactivates", oa=4, ob=4)
    return g.save()


def state_facebook():
    g = Graph("st_fb", 170, 56)
    g.node("s", 8, 28, 0, 0, "", "start")
    g.node("none", 30, 28, 28, 16, "not connected", "round", fs=6.2)
    g.node("auth", 90, 28, 34, 16, "waiting for\nPage choice", "round", fs=6.2)
    g.node("con", 150, 28, 30, 16, "connected", "round", fs=6.2)
    g.edge("s", "none", "r", "l")
    g.edge("none", "auth", "r", "l", "owner logs in to\nFacebook (OAuth)")
    g.edge("auth", "con", "r", "l", "owner picks\na Page")
    g.edge("con", "none", "b", "b", "owner disconnects", via=[(150, 48), (30, 48)], label_at=0.5)
    g.edge("auth", "none", "t", "t", "list expires (10 min)", via=[(90, 8), (30, 8)], label_at=0.5)
    return g.save()


def state_order_collect():
    g = Graph("st_collect", 170, 56)
    g.node("s", 8, 28, 0, 0, "", "start")
    g.node("none", 32, 28, 28, 16, "no pending\norder", "round", fs=6.2)
    g.node("col", 84, 28, 38, 18, "collecting\n(fields missing;\nasks again if invalid)", "round", fs=6.0)
    g.node("rdy", 128, 28, 28, 16, "ready\n(all valid)", "round", fs=6.2)
    g.node("dr", 160, 28, 18, 16, "draft\ncreated", "round", fs=5.8)
    g.edge("s", "none", "r", "l")
    g.edge("none", "col", "r", "l", "customer wants\nto order")
    g.edge("col", "rdy", "r", "l")
    g.edge("rdy", "dr", "r", "l")
    g.edge("dr", "none", "b", "b", "pending order cleared", via=[(160, 50), (32, 50)], label_at=0.5)
    return g.save()


# ------------------------------------------------------------------------------------------------ ER diagrams
SHORT = {"TIMESTAMP WITH TIME ZONE": "timestamptz", "DATETIME": "timestamptz", "ARRAY": "varchar[]", "VARCHAR": "varchar", "INTEGER": "int", "BOOLEAN": "bool", "NUMERIC": "numeric",
         "TEXT": "text", "JSONB": "jsonb", "BIGINT": "bigint", "DATE": "date", "FLOAT": "float", "JSON": "json"}


def rows_for(table, only=None):
    out = []
    cols = INV["tables"][table]["columns"]
    for c in cols:
        if only and c["name"] not in only:
            continue
        t = str(c["type"]).replace("VARCHAR(", "varchar(")
        for k, v in SHORT.items():
            if t.startswith(k):
                t = t.replace(k, v, 1)
        t = t.replace("VECTOR", "vector").replace("NUMERIC", "numeric")
        tag = "PK" if c["pk"] else ("FK" if c["fk"] else "  ")
        out.append(f"{tag} {c['name']} : {t}")
    return out


class ER:
    def __init__(self, name, w, h):
        self.c = Canvas(w, h, name)
        self.b = {}

    def add(self, key, x, y, w):
        self.b[key] = table_box(self.c, x, y, w, key, rows_for(key), fs=5.4, row_h=3.15, title_h=4.8)

    def a(self, key, side, off=0.0):
        x, y, w, h = self.b[key]
        return {"l": (x, y + h / 2 + off), "r": (x + w, y + h / 2 + off), "t": (x + w / 2 + off, y), "b": (x + w / 2 + off, y + h)}[side]

    def mark(self, p, q, lab):
        dx, dy = q[0] - p[0], q[1] - p[1]
        d = math.hypot(dx, dy) or 1
        self.c.text(p[0] + dx / d * 3.0 + (-dy / d) * 2.0, p[1] + dy / d * 3.0 + (dx / d) * 2.0, lab, 6.0, bold=True)

    def link(self, pts):
        """pts run from the parent (1) to the child (N)."""
        self.c.line(pts, lw=0.8)
        self.mark(pts[0], pts[1], "1")
        self.mark(pts[-1], pts[-2], "N")

    def bus(self, parent_pt, children, bus_y, extra_x=None):
        px, py = parent_pt
        xs = [self.a(k, "t")[0] for k in children]
        x0, x1 = min(xs + [px]), max(xs + [px] + ([extra_x] if extra_x else []))
        self.c.line([(px, py), (px, bus_y)], lw=0.8)
        self.mark((px, py), (px, bus_y), "1")
        self.c.line([(x0, bus_y), (x1, bus_y)], lw=0.8)
        for k in children:
            x, y = self.a(k, "t")
            self.c.line([(x, bus_y), (x, y)], lw=0.8)
            self.mark((x, y), (x, bus_y), "N")

    def save(self):
        return self.c.save()


def er_auth():
    e = ER("er_auth", 170, 112)
    e.add("plans", 4, 4, 42); e.add("shops", 64, 4, 42); e.add("simulated_payments", 124, 4, 44)
    e.add("users", 4, 44, 50); e.add("shop_message_usage", 64, 52, 46); e.add("admin_actions", 124, 46, 44)
    e.add("password_reset_tokens", 4, 84, 50)
    e.link([e.a("plans", "r"), e.a("shops", "l")])
    e.link([e.a("shops", "r"), e.a("simulated_payments", "l")])
    s = e.a("shops", "b", -12)
    e.link([s, (s[0], 36), (e.a("users", "t")[0], 36), e.a("users", "t")])
    e.link([e.a("shops", "b", 2), e.a("shop_message_usage", "t")])
    e.link([(106, 20), (115, 20), (115, 58), (124, 58)])
    e.link([e.a("users", "b"), e.a("password_reset_tokens", "t")])
    e.c.text(146, 100, "admin_actions also has a foreign key\nto users (admin_user_id, SET NULL).", 5.6)
    return e.save()


def er_catalog():
    e = ER("er_catalog", 170, 132)
    e.add("shops", 64, 4, 42)
    e.add("products", 4, 44, 52); e.add("shop_policies", 60, 44, 48); e.add("delivery_areas", 112, 44, 40)
    e.add("ai_usage_logs", 4, 94, 52); e.add("embedding_chunks", 64, 94, 54)
    sx, sy = e.a("shops", "b")
    e.bus((sx, sy), ["products", "shop_policies", "delivery_areas"], 36, extra_x=160)
    e.c.line([(160, 36), (160, 89)], lw=0.8)
    e.c.line([(160, 89), (e.a("ai_usage_logs", "t")[0], 89)], lw=0.8)
    for k in ("ai_usage_logs", "embedding_chunks"):
        x, y = e.a(k, "t")
        e.c.line([(x, 89), (x, y)], lw=0.8)
        e.mark((x, y), (x, 89), "N")
    return e.save()


def er_conv():
    e = ER("er_conv", 170, 178)
    e.add("shops", 4, 8, 34); e.add("facebook_pages", 44, 8, 44); e.add("weekly_insights", 94, 8, 44)
    e.add("chats", 4, 44, 54); e.add("messages", 66, 44, 50)
    e.add("orders", 4, 108, 54); e.add("handover_events", 66, 108, 46); e.add("notifications", 118, 108, 48)
    e.link([e.a("shops", "r", -4), e.a("facebook_pages", "l", -4)])
    e.c.line([(21, 8), (21, 3), (116, 3), (116, 8)], lw=0.8)
    e.mark((21, 8), (21, 3), "1"); e.mark((116, 8), (116, 3), "N")
    e.link([(21, e.a("shops", "b")[1]), (21, 44)])
    e.link([e.a("chats", "r"), e.a("messages", "l")])
    cx, cy = e.a("chats", "b")
    e.bus((cx, cy), ["orders", "handover_events", "notifications"], 103)
    e.c.text(142, 64, "Every table here also has\nshop_id (FK to shops,\nON DELETE CASCADE).\nweekly_insights joins shops\nwith the same rule.", 5.8)
    return e.save()


def er_overview_save():
    g = Graph("er_overview", 170, 136, fs=6.0)
    P = {"shops": (85, 48), "plans": (22, 10), "simulated_payments": (22, 28), "shop_message_usage": (22, 46), "password_reset_tokens": (22, 74), "users": (22, 90),
         "admin_actions": (22, 120), "products": (148, 10), "shop_policies": (148, 26), "delivery_areas": (148, 42), "embedding_chunks": (148, 58), "ai_usage_logs": (148, 74),
         "facebook_pages": (62, 12), "weekly_insights": (108, 12), "chats": (85, 74), "messages": (48, 104), "orders": (75, 104), "handover_events": (100, 104), "notifications": (128, 104)}
    rel = [("shops", "plans"), ("simulated_payments", "shops"), ("shop_message_usage", "shops"), ("users", "shops"), ("password_reset_tokens", "users"), ("admin_actions", "users"),
           ("products", "shops"), ("shop_policies", "shops"), ("delivery_areas", "shops"), ("embedding_chunks", "shops"), ("ai_usage_logs", "shops"), ("facebook_pages", "shops"),
           ("weekly_insights", "shops"), ("chats", "shops"), ("messages", "chats"), ("orders", "chats"), ("handover_events", "chats"), ("notifications", "chats")]
    for ch, pa in rel:
        g.line([P[ch], P[pa]], lw=0.7)
    for k, (x, y) in P.items():
        g.node(k, x, y, 27 if y == 104 else (40 if len(k) > 14 else 32), 8, k, "box", fs=5.0 if y == 104 else 5.6)
    g.text(85, 128, "Each line is a foreign key from the child table to its parent (one parent, many children).", fs=5.8)
    return g.save()


# ------------------------------------------------------------------------------------------------ wireframes
def wire_frame(name, title, w, h, draw):
    c = Canvas(w, h, name)
    c.ax.add_patch(__import__("matplotlib").patches.Rectangle((2, 2), w - 4, h - 4, fc="white", ec="black", lw=1.1, zorder=1))
    c.text(w / 2, 6.5, title, 7, bold=True)
    c.line([(2, 11), (w - 2, 11)], lw=0.6)
    draw(c)
    return c.save()


def wf_login():
    def d(c):
        c.box(45, 22, 80, 70, "", rounded=False)
        c.text(85, 30, "Log in to ShopSathi", 8, bold=True)
        c.box(55, 40, 60, 8, "E-mail", fs=6.5, rounded=False, align="left")
        c.box(55, 54, 60, 8, "Password", fs=6.5, rounded=False, align="left")
        c.box(55, 68, 60, 8, "Log in", fs=7, bold=True, rounded=False)
        c.text(85, 84, "Forgot password?     Create an account", 6.2)
    return wire_frame("wf_login", "Wireframe: login page", 170, 100, d)


def wf_shell():
    def d(c):
        c.box(6, 15, 158, 9, "Shop name | Dashboard  Inbox  Orders  Reports  Products  Shop policy  Test chat  Facebook Page  My plan  Staff  Settings | bell | Log out", fs=5.6, rounded=False)
        c.box(10, 30, 150, 12, "Page title and main action button", fs=7, bold=True, rounded=False)
        c.box(10, 48, 150, 56, "Page content: forms, tables or cards.\nOn a phone the menu becomes a drop-down and\nthe tables scroll sideways inside their box.", fs=7, rounded=False, dashed=True)
    return wire_frame("wf_shell", "Wireframe: seller dashboard layout", 170, 112, d)


def wf_inbox():
    def d(c):
        c.box(6, 16, 56, 8, "All | Flagged (n)", fs=6.5, rounded=False)
        for i in range(4):
            c.box(6, 27 + i * 17, 56, 15, f"Customer {i+1}   date\nlast message...  [Flagged] [AI paused]", fs=5.8, rounded=False, align="left")
        c.box(6, 96, 56, 7, "Load more", fs=6.2, rounded=False)
        c.box(68, 16, 96, 8, "Customer name        [Pause AI / Resume AI]  [Mark handled]", fs=6.2, rounded=False)
        c.box(68, 27, 96, 62, "Conversation\n\nCustomer bubble (left)\nAI bubble (right, labelled AI)\nSeller bubble (right, labelled Seller)\nOrder draft or product card", fs=6.5, rounded=False, dashed=True)
        c.box(68, 93, 80, 10, "Type a reply...", fs=6.3, rounded=False, align="left")
        c.box(150, 93, 14, 10, "Send", fs=6.3, rounded=False)
    return wire_frame("wf_inbox", "Wireframe: Inbox", 170, 108, d)


def wf_orders():
    def d(c):
        c.box(6, 16, 100, 8, "Draft (n) | Confirmed (n) | Cancelled (n)", fs=6.5, rounded=False)
        c.box(6, 28, 158, 8, "Order | Customer | Product | Qty | Total | Created | Review", fs=6.2, rounded=False, bold=True)
        for i in range(3):
            c.box(6, 36 + i * 9, 158, 9, f"#{30-i} | name, phone | product, size | 1 | total | date | Review", fs=6, rounded=False, align="left")
        c.box(6, 68, 158, 28, "Export confirmed orders (CSV) for the courier\nFrom date [ ]   To date [ ]   [Export]", fs=6.5, rounded=False, dashed=True)
    return wire_frame("wf_orders", "Wireframe: Orders list and CSV export", 170, 102, d)


ALL = dict(uc_setup=uc_seller_setup, uc_daily=uc_daily, uc_customer=uc_customer, uc_admin=uc_admin, st_order=state_order, st_chat=state_chat,
           st_msg=state_message, st_shop=state_shop, st_fb=state_facebook, st_collect=state_order_collect, er_auth=er_auth, er_catalog=er_catalog,
           er_conv=er_conv, wf_login=wf_login, wf_shell=wf_shell, wf_inbox=wf_inbox, wf_orders=wf_orders)


ALL["er_overview"] = er_overview_save

if __name__ == "__main__":
    import sys

    for k, f in ALL.items():
        if len(sys.argv) > 1 and k not in sys.argv[1:]:
            continue
        print(f())
