"""Display only, for tools/agent.py: terminal colours and the camera-window HUD, in the style of the judges' page
(Blueprint: navy #13294B, the zone colours of the page, and the zone words place it / ask / move it).

Nothing here changes what the agent decides, logs or asks; agent.py calls these functions only to print and to draw
on the image it shows. Colours are off when the output is not a terminal (tests, files), so the text stays plain.
"""
import os
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
TOP_H, BOTTOM_H = 44, 40

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
        return cv2.putText(img, s, org, color, _FACE, size, weight)[0][0]
    cv2.putText(img, _ascii(s), org, cv2.FONT_HERSHEY_SIMPLEX, size / 30.0, color, max(1, weight // 300), cv2.LINE_AA)
    return org[0] + text_w(s, size, weight)


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


def _logo(img, x, y):
    for i, dx in enumerate((5, 0, 0)):                 # three blocks, the top one shifted right (as on the page)
        y0 = y + i * 9
        cv2.rectangle(img, (x + dx, y0), (x + dx + 17, y0 + 7), BGR["BRAND"], -1)
        cv2.rectangle(img, (x + dx, y0), (x + dx + 17, y0 + 7), BGR["EDGE"], 1)


def top_bar(img, right=""):
    w = img.shape[1]
    panel(img, 0, 0, w, TOP_H, BGR["NAVY"], 0.82)
    _logo(img, 14, 9)
    text(img, "Drystone", (44, 30), 21, BGR["WHITE"], 700)       # as the logo on the page
    if right:
        text(img, right, (w - 16 - text_w(right, 17), 29), 17, BGR["WHITE"], 500)


def _dashed(img, p, q, color, thick=2, dash=10):
    p, q = np.array(p, float), np.array(q, float)
    n = max(1, int(np.linalg.norm(q - p) // dash))
    for i in range(0, n, 2):
        a, b = p + (q - p) * i / n, p + (q - p) * min(n, i + 1) / n
        cv2.line(img, tuple(int(v) for v in a), tuple(int(v) for v in b), color, thick, cv2.LINE_AA)


LEGEND = (("marker", "EDGE", False), ("stack", "WHITE", False), ("suggested spot", "BRAND", True), ("next box", "MUTED", False))


def bottom_bar(img, keys):
    h, w = img.shape[:2]
    panel(img, 0, h - BOTTOM_H, w, h, BGR["NAVY"], 0.82)
    text(img, keys, (16, h - 14), 16, BGR["WHITE"], 500)
    x = w - 16
    for name, col, dashed in reversed(LEGEND):
        tw = text_w(name, 14)
        x -= tw
        text(img, name, (x, h - 15), 14, BGR["MUTED"], 400)
        x -= 28
        if dashed:
            _dashed(img, (x, h - 20), (x + 22, h - 20), BGR[col], 3, 6)
        else:
            cv2.line(img, (x, h - 20), (x + 22, h - 20), BGR[col], 3, cv2.LINE_AA)
        x -= 18


def pill(img, s, y, kind="warn", x=16, size=17):
    """A rounded label: warn (yellow), alert (orange), info (navy)."""
    fill, ink = {"warn": (BGR["YELLOW"], BGR["INK"]), "alert": (BGR["ORANGE"], BGR["WHITE"]),
                 "info": (BGR["NAVY"], BGR["WHITE"])}[kind]
    w = text_w(s, size) + 26
    h = size + 16
    r = h // 2
    over = img.copy()
    cv2.rectangle(over, (x + r, y), (x + w - r, y + h), fill, -1)
    cv2.circle(over, (x + r, y + r), r, fill, -1, cv2.LINE_AA)
    cv2.circle(over, (x + w - r, y + r), r, fill, -1, cv2.LINE_AA)
    cv2.addWeighted(over, 0.9, img, 0.1, 0, dst=img)
    if kind == "warn":
        cv2.circle(img, (x + 14, y + r), 4, BGR["INK"], -1, cv2.LINE_AA)
        text(img, s, (x + 24, y + h - 9), size, ink, 600)
    else:
        text(img, s, (x + 13, y + h - 9), size, ink, 600)
    return y + h + 8


def decision_banner(img, d, hint=""):
    """The decision as a card in the zone colour: zone word, action code, P(fall), safer spot."""
    z = d["zone"]
    fill, ink = BGR[z], ZONE_INK[z]
    x0, y0 = 16, TOP_H + 14
    lines = [f"P(fall) {d['p']:.0%}", f"at {d['offset_m'] * 100:+.0f} cm · overhang {d['overhang_pct']:+.0f}%"]
    if d.get("alternative"):
        a = d["alternative"]
        lines.append(f"Safer spot {a['offset_m'] * 100:+.0f} cm · P(fall) {a['p']:.0%}")
    head = f"{z} · {SAY[z]}"
    w = max(text_w(head, 40, 700) + text_w(d["action"], 15, 700) + 46, text_w(lines[0], 46, 700),
            *(text_w(s, 19, 500) for s in lines[1:]), text_w(hint, 16) if hint else 0) + 36
    h = 70 + 56 + 28 * (len(lines) - 1) + (30 if hint else 0)
    panel(img, x0, y0, x0 + w, y0 + h, fill, 0.9)
    xe = text(img, head, (x0 + 18, y0 + 50), 40, ink, 700)
    bw = text_w(d["action"], 15, 700) + 16
    cv2.rectangle(img, (xe + 14, y0 + 24), (xe + 14 + bw, y0 + 50), ink, 1, cv2.LINE_AA)
    text(img, d["action"], (xe + 22, y0 + 43), 15, ink, 700)
    text(img, lines[0], (x0 + 18, y0 + 108), 46, ink, 700)
    y = y0 + 108
    for s in lines[1:]:
        y += 28
        text(img, s, (x0 + 18, y), 19, ink, 500)
    if hint:
        text(img, hint, (x0 + 18, y + 30), 16, ink, 500)


def check_banner(img, status, message, zone_now=None, p_now=None):
    """After placement: OK / OFF_PLAN / FELL in colour, with the agent's message (shortened)."""
    fill = {"OK": BGR["GREEN"], "OFF_PLAN": BGR["YELLOW"], "FELL": BGR["RED"], "FELL?": BGR["RED"]}.get(status, BGR["NAVY"])
    ink = BGR["INK"] if status == "OFF_PLAN" else BGR["WHITE"]
    x0, y0 = 16, TOP_H + 14
    msg = message if len(message) <= 78 else message[:77] + "…"
    sub = f"stack now: {zone_now} · {SAY.get(zone_now, '')}, P(fall) {p_now:.0%}" if zone_now else ""
    w = max(text_w("CHECK  " + status, 34, 700), text_w(msg, 17), text_w(sub, 17) if sub else 0) + 36
    h = 98 + (26 if sub else 0)
    panel(img, x0, y0, x0 + w, y0 + h, fill, 0.9)
    xe = text(img, "CHECK", (x0 + 18, y0 + 46), 20, ink, 600)
    text(img, status, (xe + 12, y0 + 48), 34, ink, 700)
    text(img, msg, (x0 + 18, y0 + 80), 17, ink, 500)
    if sub:
        text(img, sub, (x0 + 18, y0 + 106), 17, ink, 500)


def waiting(img, dots=3):
    """While a decision is computed on AWS Lambda (a static card: the request blocks the window)."""
    s = "Simulating on AWS Lambda…"
    w = text_w(s, 26, 600) + 40
    x0, y0 = 16, TOP_H + 14
    panel(img, x0, y0, x0 + w, y0 + 58, BGR["NAVY"], 0.88)
    text(img, s, (x0 + 20, y0 + 38), 26, BGR["WHITE"], 600)


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
