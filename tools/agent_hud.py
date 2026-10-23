"""Display only, for tools/agent.py: terminal colours and the camera-window HUD, in the style of the judges' page
(Blueprint: navy #13294B, the zone colours of the page, and the zone words place it / ask / move it).

Nothing here changes what the agent decides, logs or asks; agent.py calls these functions only to print and to draw
on the image it shows. Colours are off when the output is not a terminal (tests, files), so the text stays plain.
"""
import functools
import os
import re
import sys
import time

import cv2
import numpy as np

SAY = {"GREEN": "place it", "YELLOW": "ask", "RED": "move it"}

# ---------------------------------------------------------------- terminal

_HEX = {"GREEN": "267D47", "YELLOW": "E2AE1C", "RED": "C93A25", "NAVY": "13294B", "BRAND": "2457C5",
        "EDGE": "8FB0F0", "MUTED": "8A93A3", "WARN": "E2AE1C"}


def _ansi_on():
    if os.environ.get("NO_COLOR") or not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return False
    if os.name == "nt":
        os.system("")             # switches the Windows console to VT mode so escape codes render
    return True


COLOR = _ansi_on()


def _rgb(hex6, bg=False):
    r, g, b = int(hex6[0:2], 16), int(hex6[2:4], 16), int(hex6[4:6], 16)
    return f"\033[{48 if bg else 38};2;{r};{g};{b}m"


def paint(s, fg=None, bg=None, bold=False, dim=False):
    """s with colours when the output is a terminal, else s unchanged."""
    if not COLOR:
        return s
    pre = ("\033[1m" if bold else "") + ("\033[2m" if dim else "")
    pre += _rgb(_HEX[fg]) if fg else ""
    pre += _rgb(_HEX[bg], bg=True) if bg else ""
    return f"{pre}{s}\033[0m" if pre else s


def zone_tag(zone):
    """[RED · move it] on the zone colour."""
    if zone not in SAY:
        return f"[{zone}]"
    ink = "NAVY" if zone == "YELLOW" else None
    tag = f"[{zone} · {SAY[zone]}]"
    if not COLOR:
        return tag
    return paint(f" {zone} · {SAY[zone]} ", fg=ink, bg=zone, bold=True) if ink else \
        f"\033[1;97m{_rgb(_HEX[zone], bg=True)} {zone} · {SAY[zone]} \033[0m"


def rule(width=72):
    return paint("─" * width, fg="EDGE", dim=True)


def label(text, kind="BRAND"):
    """A short bold label on a coloured background, e.g. SUPERVISOR."""
    if not COLOR:
        return f"== {text} =="
    ink = "NAVY" if kind in ("YELLOW", "WARN") else None
    return paint(f" {text} ", fg=ink, bg=kind, bold=True) if ink else f"\033[1;97m{_rgb(_HEX[kind], bg=True)} {text} \033[0m"


STATUS_ZONE = {"OK": "GREEN", "OFF_PLAN": "YELLOW", "FELL": "RED", "FELL?": "RED", "NOT_PLACED": "BRAND"}


def status_tag(status):
    z = STATUS_ZONE.get(status)
    if not COLOR or z is None:
        return status
    ink = "NAVY" if z == "YELLOW" else None
    return paint(f" {status} ", fg=ink, bg=z, bold=True) if ink else f"\033[1;97m{_rgb(_HEX[z], bg=True)} {status} \033[0m"


def banner(camera, calib, decisions):
    """Opening block: name, then camera, calibration and where decisions are computed (never the URL)."""
    print()
    print(paint("Drystone", fg="EDGE", bold=True) + paint(" · Every stack is a drystone wall", bold=True))
    print(rule())
    for k, v in (("Camera", camera), ("Calibration", calib), ("Decisions", decisions)):
        print(f"  {paint(f'{k:<13}', fg='MUTED')}{v}")
    print()
    for k, v in (("A / D", "move candidate 1 cm"), ("SPACE", "decide / check"), ("X", "cancel"), ("Q", "quit")):
        print(f"  {paint(f'{k:<8}', fg='EDGE', bold=True)}{v}")
    print()
    for s in ("The camera reads the stack and draws the next box as a wireframe.",
              "SPACE: the agent decides. GREEN · place it, YELLOW · ask, RED · move it.",
              "Place the box in the wireframe, let go, SPACE: the agent checks it.",
              "Every step is logged in data/agent_<time>/log.jsonl with a photo."):
        print(f"  {paint(s, dim=True)}")
    print(rule())


def decision_block(d):
    """One block per decision: zone, P(fall), shift, safer spot, action code; the trace below, dimmed."""
    shift = d["offset_m"] * 100
    head = f"{zone_tag(d['zone'])}  P(fall) {d['p']:.0%}  at {shift:+.0f} cm"
    if d.get("alternative"):
        a = d["alternative"]
        head += f"  →  safer spot {a['offset_m'] * 100:+.0f} cm (P {a['p']:.0%})"
    head += f"  ({d['action']})"
    src = d.get("source", "")
    where = "AWS Lambda" if src == "aws" else src
    print()
    print(rule())
    print(" " + head)
    print("   " + paint(f"box ID {d['box_id']} · overhang {d['overhang_pct']:+.0f}% · ±{d['ci']:.0%} "
                        f"· {d['n']} simulations" + (f" · {where}" if where else ""), fg="MUTED"))
    for line in d["trace"]:
        print("   " + paint(f"- {line}", dim=True))


# ---------------------------------------------------------------- camera window

BGR = {"NAVY": (75, 41, 19), "BRAND": (197, 87, 36), "EDGE": (240, 176, 143), "WHITE": (255, 255, 255),
       "INK": (43, 40, 38), "GREEN": (71, 125, 38), "YELLOW": (28, 174, 226), "RED": (37, 58, 201),
       "MUTED": (190, 180, 168), "ORANGE": (26, 120, 230)}
ZONE_INK = {"GREEN": BGR["WHITE"], "YELLOW": BGR["INK"], "RED": BGR["WHITE"]}
TOP_H, BOTTOM_H = 44, 44
M, PAD, GAP = 16, 16, 12        # outer margin, inner side padding, space between elements (px)
MIN_SIZE = 13

try:
    _FACE = cv2.FontFace("sans")
    cv2.putText(np.zeros((2, 2, 3), np.uint8), "x", (0, 1), (0, 0, 0), _FACE, 10, 400)
except Exception:                                   # older OpenCV: Hershey with anti-aliasing
    _FACE = None
TEXT_ENGINE = "cv2.FontFace('sans') (OpenCV 5 text API)" if _FACE is not None else "Hershey + LINE_AA"
_ASCII = {"·": "-", "→": "->", "…": "...", "±": "+-"}


def _ascii(s):
    for a, b in _ASCII.items():
        s = s.replace(a, b)
    return s


def text_w(s, size, weight=500):
    if _FACE is not None:
        return cv2.putText(np.zeros((2, 2, 3), np.uint8), s, (0, 1), (0, 0, 0), _FACE, size, weight)[0][0]
    (w, _), _ = cv2.getTextSize(_ascii(s), cv2.FONT_HERSHEY_SIMPLEX, size / 30.0, max(1, weight // 300))
    return w


def text(img, s, org, size=20, color=BGR["WHITE"], weight=500):
    """Text with its baseline at org; returns the x after it."""
    org = (int(org[0]), int(org[1]))
    if _FACE is not None:
        parts = re.split(r"(?<!\w)(Q)(?!\w)", s)        # the Q key: its tail is too short in this font
        x = org[0]
        for i, part in enumerate(parts):
            if not part:
                continue
            x0 = x
            x = cv2.putText(img, part, (x, org[1]), color, _FACE, size, weight)[0][0]
            if i % 2:                                   # draw a longer tail so it does not read as O
                cap, q = metrics(size, weight)[0], x - x0
                cv2.line(img, (round(x0 + 0.52 * q), round(org[1] - 0.3 * cap)),
                         (round(x0 + 1.02 * q), round(org[1] + 0.16 * cap)), color, max(2, round(size / 8)),
                         cv2.LINE_AA)
        return x
    cv2.putText(img, _ascii(s), org, cv2.FONT_HERSHEY_SIMPLEX, size / 30.0, color, max(1, weight // 300), cv2.LINE_AA)
    return org[0] + text_w(s, size, weight)


@functools.lru_cache(maxsize=None)
def metrics(size, weight=500):
    """(cap, desc) in px: ink height of capitals above the baseline, and of descenders below it."""
    def ink(s):
        c = np.zeros((size * 3, text_w(s, size, weight) + 8, 3), np.uint8)
        text(c, s, (2, size * 2), size, (255, 255, 255), weight)
        rows = np.nonzero(c.max(axis=(1, 2)))[0]
        return size * 2 - rows[0], max(0, rows[-1] - size * 2 + 1)
    return int(ink("H")[0]), int(ink("gjpqy(")[1])


def fit(s, size, weight, maxw):
    """Lines and size so that every line is at most maxw wide: shrink a little, then wrap (nothing is cut)."""
    smallest = max(MIN_SIZE, round(size * 0.85))
    for sz in range(size, smallest - 1, -1):
        if text_w(s, sz, weight) <= maxw:
            return [s], sz
    lines, cur = [], ""
    for word in s.split(" "):
        t = word if not cur else cur + " " + word
        if cur and text_w(t, smallest, weight) > maxw:
            lines.append(cur)
            cur = word
        else:
            cur = t
    return lines + [cur], smallest


def panel(img, x0, y0, x1, y1, color, alpha=0.85):
    """A filled rectangle blended with cv2.addWeighted."""
    h, w = img.shape[:2]
    x0, y0, x1, y1 = max(0, int(x0)), max(0, int(y0)), min(w, int(x1)), min(h, int(y1))
    if x1 <= x0 or y1 <= y0:
        return
    roi = img[y0:y1, x0:x1]
    fill = np.empty_like(roi)
    fill[:] = color
    cv2.addWeighted(fill, alpha, roi, 1 - alpha, 0, dst=roi)


def rounded(img, x0, y0, x1, y1, r, color, alpha=0.9):
    """A filled rounded rectangle blended with cv2.addWeighted."""
    over = img.copy()
    cv2.rectangle(over, (x0 + r, y0), (x1 - r, y1), color, -1)
    cv2.rectangle(over, (x0, y0 + r), (x1, y1 - r), color, -1)
    for cx, cy in ((x0 + r, y0 + r), (x1 - r, y0 + r), (x0 + r, y1 - r), (x1 - r, y1 - r)):
        cv2.circle(over, (cx, cy), r, color, -1, cv2.LINE_AA)
    cv2.addWeighted(over, alpha, img, 1 - alpha, 0, dst=img)


def _baseline(y0, y1, size, weight=500):
    """The baseline that centres capitals between y0 and y1."""
    return round((y0 + y1) / 2 + metrics(size, weight)[0] / 2)


def _logo(img, x, y):
    for i, dx in enumerate((5, 0, 0)):                 # three blocks, the top one shifted right (as on the page)
        y0 = y + i * 9
        cv2.rectangle(img, (x + dx, y0), (x + dx + 17, y0 + 7), BGR["BRAND"], -1)
        cv2.rectangle(img, (x + dx, y0), (x + dx + 17, y0 + 7), BGR["EDGE"], 1)


def top_bar(img, right=""):
    w = img.shape[1]
    panel(img, 0, 0, w, TOP_H, BGR["NAVY"], 0.82)
    _logo(img, M, (TOP_H - 25) // 2)
    xe = text(img, "Drystone", (M + 32, _baseline(0, TOP_H, 21, 700)), 21, BGR["WHITE"], 700)   # as the logo on the page
    if right:
        size = 17
        while size > 11 and text_w(right, size) > w - M - xe - 2 * GAP:
            size -= 1
        text(img, right, (w - M - text_w(right, size), _baseline(0, TOP_H, size)), size, BGR["WHITE"], 500)


def _dashed(img, p, q, color, thick=2, dash=10):
    p, q = np.array(p, float), np.array(q, float)
    n = max(1, int(np.linalg.norm(q - p) // dash))
    for i in range(0, n, 2):
        a, b = p + (q - p) * i / n, p + (q - p) * min(n, i + 1) / n
        cv2.line(img, tuple(int(v) for v in a), tuple(int(v) for v in b), color, thick, cv2.LINE_AA)


LEGEND = (("marker", "EDGE", False), ("stack", "WHITE", False), ("suggested spot", "BRAND", True), ("next box", "MUTED", False))


def _legend_w(size):
    return sum(text_w(name, size, 400) + 46 for name, _, _ in LEGEND) - 18


def bottom_bar(img, keys):
    h, w = img.shape[:2]
    y0 = h - BOTTOM_H
    panel(img, 0, y0, w, h, BGR["NAVY"], 0.82)
    ks, ls = 16, 14
    while ks > 11 and text_w(keys, ks) + 2 * GAP + _legend_w(ls) > w - 2 * M:
        ks, ls = ks - 1, max(11, ls - 1)
    text(img, keys, (M, _baseline(y0, h, ks)), ks, BGR["WHITE"], 500)
    if text_w(keys, ks) + 2 * GAP + _legend_w(ls) > w - 2 * M:
        return                                         # a very narrow frame: the keys only
    by = _baseline(y0, h, ls, 400)
    mid = by - metrics(ls, 400)[0] // 2
    x = w - M
    for name, col, dashed in reversed(LEGEND):
        x -= text_w(name, ls, 400)
        text(img, name, (x, by), ls, BGR["MUTED"], 400)
        x -= 28
        if dashed:
            _dashed(img, (x, mid), (x + 22, mid), BGR[col], 3, 6)
        else:
            cv2.line(img, (x, mid), (x + 22, mid), BGR[col], 3, cv2.LINE_AA)
        x -= 18


PILL_SIZE, PILL_VPAD, PILL_GAP = 17, 11, 8
PILL_COLORS = {"warn": (BGR["YELLOW"], BGR["INK"]), "alert": (BGR["ORANGE"], BGR["WHITE"]),
               "info": (BGR["NAVY"], BGR["WHITE"])}


def pills(img, notes):
    """Rounded labels stacked upward from the bottom bar: warn (yellow, with a dot), alert (orange), info (navy)."""
    h, w = img.shape[:2]
    y = h - BOTTOM_H - GAP
    for s, kind in reversed(notes):
        fill, ink = PILL_COLORS[kind]
        lead = PAD + 16 if kind == "warn" else PAD       # the warn dot sits in front of the text
        lines, size = fit(s, PILL_SIZE, 600, w - 2 * M - lead - PAD)
        cap = metrics(size, 600)[0]
        step = round(size * 1.4)
        ph = cap + 2 * PILL_VPAD + step * (len(lines) - 1)
        pw = lead + max(text_w(t, size, 600) for t in lines) + PAD
        y -= ph
        rounded(img, M, y, M + pw, y + ph, (cap + 2 * PILL_VPAD) // 2, fill, 0.9)
        by = y + PILL_VPAD + cap
        if kind == "warn":
            cv2.circle(img, (M + PAD + 4, by - cap // 2), 4, BGR["INK"], -1, cv2.LINE_AA)
        for t in lines:
            text(img, t, (M + lead, by), size, ink, 600)
            by += step
        y -= PILL_GAP


def _card(img, rows, fill, ink, alpha=0.9):
    """A card under the top bar. Each row: {"segs": [(text, size, weight), ...] on one baseline,
    "badge": (text, size) after them, "gap": px above the row}. Long one-part rows shrink a little, then wrap."""
    x0, y0 = M, TOP_H + GAP
    maxw = img.shape[1] - 2 * M - 2 * PAD
    out = []                                           # (segs, badge, gap) after fitting
    for row in rows:
        segs, badge, gap = row["segs"], row.get("badge"), row.get("gap", 0)
        if len(segs) == 1 and not badge:
            s, size, weight = segs[0]
            lines, size = fit(s, size, weight, maxw)
            out += [([(t, size, weight)], None, gap if i == 0 else round(size * 0.4)) for i, t in enumerate(lines)]
        else:
            out.append((segs, badge, gap))

    def row_w(segs, badge):
        x = sum(text_w(t, s, wt) for t, s, wt in segs) + 12 * (len(segs) - 1)
        return x + (14 + text_w(badge[0], badge[1], 700) + 16 if badge else 0)

    cw = max(row_w(s, b) for s, b, _ in out) + 2 * PAD
    y, bys = y0 + PAD, []
    for segs, _, gap in out:
        y += gap + max(metrics(s, wt)[0] for _, s, wt in segs)
        bys.append(y)
        y += max(metrics(s, wt)[1] for _, s, wt in segs)
    ch = y + PAD - y0
    panel(img, x0, y0, x0 + cw, y0 + ch, fill, alpha)
    for (segs, badge, _), by in zip(out, bys):
        x = x0 + PAD
        for t, s, wt in segs:
            x = text(img, t, (x, by), s, ink, wt) + 12
        if badge:                                      # the action code in a box, centred on the capitals
            bt, bs = badge
            cb = metrics(bs, 700)[0]
            mid = by - metrics(segs[-1][1], segs[-1][2])[0] // 2
            bx, bb = x + 2, mid + cb - cb // 2
            cv2.rectangle(img, (bx, bb - cb - 8), (bx + text_w(bt, bs, 700) + 16, bb + 8), ink, 1, cv2.LINE_AA)
            text(img, bt, (bx + 8, bb), bs, ink, 700)
    return y0 + ch


def decision_banner(img, d, hint=""):
    """The decision as a card in the zone colour: zone word, action code, P(fall), safer spot."""
    z = d["zone"]
    rows = [{"segs": [(f"{z} · {SAY[z]}", 40, 700)], "badge": (d["action"], 15)},
            {"segs": [(f"P(fall) {d['p']:.0%}", 46, 700)], "gap": 18},
            {"segs": [(f"at {d['offset_m'] * 100:+.0f} cm · overhang {d['overhang_pct']:+.0f}%", 19, 500)], "gap": 12}]
    if d.get("alternative"):
        a = d["alternative"]
        rows.append({"segs": [(f"Safer spot {a['offset_m'] * 100:+.0f} cm · P(fall) {a['p']:.0%}", 19, 500)], "gap": 9})
    if hint:
        rows.append({"segs": [(hint, 16, 500)], "gap": 14})
    _card(img, rows, BGR[z], ZONE_INK[z])


def check_banner(img, status, message, zone_now=None, p_now=None):
    """After placement: OK / OFF_PLAN / FELL in colour, with the agent's message (wrapped, never cut)."""
    fill = {"OK": BGR["GREEN"], "OFF_PLAN": BGR["YELLOW"], "FELL": BGR["RED"], "FELL?": BGR["RED"]}.get(status, BGR["NAVY"])
    ink = BGR["INK"] if status == "OFF_PLAN" else BGR["WHITE"]
    rows = [{"segs": [("CHECK", 20, 600), (status, 34, 700)]}, {"segs": [(message, 17, 500)], "gap": 14}]
    if zone_now:
        rows.append({"segs": [(f"stack now: {zone_now} · {SAY.get(zone_now, '')}, P(fall) {p_now:.0%}", 17, 500)],
                     "gap": 9})
    _card(img, rows, fill, ink)


def waiting(img, dots=3):
    """While a decision is computed on AWS Lambda (a static card: the request blocks the window)."""
    _card(img, [{"segs": [("Simulating on AWS Lambda…", 26, 600)]}], BGR["NAVY"], BGR["WHITE"], 0.88)


def suggested(img, pts, thick=2):
    """A dashed wireframe (8 projected corners, index = 4*x + 2*y + z bit), as the page draws the safer spot."""
    if pts is None:
        return
    for a in range(8):
        for b in range(a + 1, 8):
            if bin(a ^ b).count("1") == 1:
                _dashed(img, pts[a], pts[b], BGR["BRAND"], thick)


def ago(t):
    return time.time() - t
