"""Generate evaluation diagrams for the Week 4 submission doc."""
from __future__ import annotations

import os
from PIL import Image, ImageDraw, ImageFont

OUT_DIR = "docs/images"
os.makedirs(OUT_DIR, exist_ok=True)

# ── Palette ─────────────────────────────────────────────────────────────────
BG      = "#1e1e2e"
WHITE   = "#cdd6f4"
SUBTLE  = "#585b70"
RED     = "#f38ba8"
RED_BG  = "#45182a"
GREEN   = "#a6e3a1"
GREEN_BG = "#1a3a26"
BLUE    = "#89b4fa"
BLUE_BG = "#1e2d50"
YELLOW  = "#f9e2af"
YELLOW_BG = "#3d2e10"
PURPLE  = "#cba6f7"

W, H = 900, 520


def _img(w=W, h=H) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (w, h), BG)
    return img, ImageDraw.Draw(img)


def _font(size: int):
    try:
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
    except Exception:
        return ImageFont.load_default()


def _box(d: ImageDraw.ImageDraw, x, y, w, h, fill, outline=None, radius=8):
    d.rounded_rectangle([x, y, x + w, y + h], radius=radius, fill=fill,
                         outline=outline or fill, width=2)


def _text(d: ImageDraw.ImageDraw, x, y, text, font, fill=WHITE, anchor="la"):
    d.text((x, y), text, font=font, fill=fill, anchor=anchor)


def _badge(d: ImageDraw.ImageDraw, cx, cy, label, font):
    r = 14
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=RED)
    d.text((cx, cy), label, font=font, fill="#1e1e2e", anchor="mm")


# ────────────────────────────────────────────────────────────────────────────
# Diagram 1 — Activity pipeline with 5 bug badges
# ────────────────────────────────────────────────────────────────────────────
def _pipeline():
    img, d = _img(W, 560)
    f_title = _font(20)
    f_label = _font(14)
    f_small = _font(12)
    f_badge = _font(13)

    _text(d, W // 2, 22, "Activity Eval Pipeline — Bug Locations", f_title, BLUE, anchor="mt")

    # ── boxes ──
    boxes = [
        (60,  140, 160, 60, BLUE_BG,   BLUE,   "Knowledge\nGraph"),
        (280, 100, 160, 60, BLUE_BG,   BLUE,   "OSM\nClassifier"),
        (280, 200, 160, 60, BLUE_BG,   BLUE,   "Tavily\nClassifier"),
        (500, 140, 160, 60, BLUE_BG,   BLUE,   "POI\nSelector"),
        (690, 140, 160, 60, BLUE_BG,   BLUE,   "rate_pois\n(LLM Synth)"),
    ]

    centers = {}
    for bx, by, bw, bh, fill, outline, label in boxes:
        _box(d, bx, by, bw, bh, fill, outline)
        cx, cy = bx + bw // 2, by + bh // 2
        centers[label.split("\n")[0]] = (cx, cy)
        for i, line in enumerate(label.split("\n")):
            d.text((cx, cy - 8 + i * 18), line, font=f_label, fill=WHITE, anchor="mm")

    # ── arrows ──
    def arrow(x1, y1, x2, y2):
        d.line([(x1, y1), (x2, y2)], fill=SUBTLE, width=2)
        d.polygon([(x2, y2), (x2 - 8, y2 - 5), (x2 - 8, y2 + 5)], fill=SUBTLE)

    arrow(220, 170, 278, 130)
    arrow(220, 170, 278, 230)
    arrow(440, 130, 498, 160)
    arrow(440, 230, 498, 180)
    arrow(660, 170, 688, 170)

    # ── bug badges ──
    bugs = [
        (220, 140, "①", "subtype field\ndropped in loader"),
        (340, 92,  "③", "name-based search\nmissing in _match()"),
        (340, 192, "②", "poi_names[:40]\nhides index >40"),
        (560, 132, "④", "fixed 1 slot\nper activity"),
        (750, 132, "⑤", "900-POI call\noverflows context"),
    ]

    for bx, by, label, desc in bugs:
        _badge(d, bx, by, label, f_badge)
        # bug callout box
        desc_x = bx + 18
        desc_y = by - 30
        lines = desc.split("\n")
        box_w = max(len(l) for l in lines) * 7 + 16
        box_h = len(lines) * 16 + 8
        _box(d, desc_x, desc_y, box_w, box_h, RED_BG, RED, radius=5)
        for i, line in enumerate(lines):
            d.text((desc_x + 8, desc_y + 4 + i * 16), line, font=f_small, fill=RED)

    # ── legend ──
    _badge(d, 62, 490, "①", f_badge)
    _text(d, 82, 483, "= Bug location", f_small, RED)

    img.save(f"{OUT_DIR}/eval_activity_pipeline.png")
    print(f"  ✓ eval_activity_pipeline.png")


# ────────────────────────────────────────────────────────────────────────────
# Diagram 2 — Subtype passthrough before/after
# ────────────────────────────────────────────────────────────────────────────
def _subtype_fix():
    img, d = _img(W, 480)
    f_title = _font(20)
    f_label = _font(14)
    f_small = _font(12)
    f_code  = _font(11)

    _text(d, W // 2, 22, "Fix ① — Subtype Passthrough", f_title, BLUE, anchor="mt")

    col_w = 380
    # Left: BEFORE
    _text(d, 90, 65, "BEFORE", f_label, RED)
    steps_before = [
        (RED_BG,   RED,   "_load_bay_area_pois()"),
        (RED_BG,   RED,   '"subtype": p.get("subtype")  ← MISSING'),
        (YELLOW_BG, YELLOW, "poi.subtype  →  None"),
        (RED_BG,   RED,   "classifier: _match(poi)"),
        (RED_BG,   RED,   "subtype lookup → KeyError → no match"),
        (RED_BG,   RED,   "result: hiking recall = 0%"),
    ]
    for i, (fill, outline, text) in enumerate(steps_before):
        y = 100 + i * 54
        _box(d, 40, y, col_w, 40, fill, outline)
        d.text((220, y + 20), text, font=f_code, fill=outline, anchor="mm")

    # Right: AFTER
    _text(d, W - 90, 65, "AFTER", f_label, GREEN, anchor="ra")
    steps_after = [
        (BLUE_BG,   BLUE,  "_load_bay_area_pois()"),
        (GREEN_BG,  GREEN, '"subtype": p.get("subtype")  ← ADDED'),
        (BLUE_BG,   BLUE,  "poi.subtype  →  'peak'"),
        (BLUE_BG,   BLUE,  "classifier: _match(poi)"),
        (GREEN_BG,  GREEN, "subtype 'peak' → hiking ✓"),
        (GREEN_BG,  GREEN, "result: hiking recall = 100%"),
    ]
    for i, (fill, outline, text) in enumerate(steps_after):
        y = 100 + i * 54
        _box(d, W - col_w - 40, y, col_w, 40, fill, outline)
        d.text((W - col_w // 2 - 40, y + 20), text, font=f_code, fill=outline, anchor="mm")

    # divider
    d.line([(W // 2, 60), (W // 2, 450)], fill=SUBTLE, width=1)

    img.save(f"{OUT_DIR}/eval_subtype_fix.png")
    print(f"  ✓ eval_subtype_fix.png")


# ────────────────────────────────────────────────────────────────────────────
# Diagram 3 — Tavily [:40] name cap
# ────────────────────────────────────────────────────────────────────────────
def _tavily_cap():
    img, d = _img(W, 520)
    f_title = _font(20)
    f_label = _font(14)
    f_small = _font(12)
    f_code  = _font(11)

    _text(d, W // 2, 22, "Fix ② — Tavily poi_names[:40] Cap", f_title, BLUE, anchor="mt")

    # list column
    list_x, list_y, list_w = 60, 65, 340
    _text(d, list_x, list_y, "poi_names list (438 POIs)", f_label, WHITE)

    visible_rows = [
        "  [0]   Alamo Square",
        "  [1]   Baker Beach",
        "  [2]   Crissy Field",
        "  ...",
        "  [38]  Twin Peaks",
        "  [39]  Sutro Tower",
    ]
    for i, row in enumerate(visible_rows):
        y = list_y + 28 + i * 22
        if row.strip() == "...":
            d.text((list_x + 8, y), row, font=f_small, fill=SUBTLE, anchor="la")
        else:
            _box(d, list_x, y, list_w, 20, BLUE_BG, BLUE, radius=3)
            d.text((list_x + 8, y + 3), row, font=f_code, fill=WHITE)

    # cut line
    cut_y = list_y + 28 + len(visible_rows) * 22 + 4
    d.line([(list_x, cut_y), (list_x + list_w, cut_y)], fill=RED, width=3)
    d.text((list_x + list_w // 2, cut_y - 14), "poi_names[:40]  ← CUT HERE", font=f_small,
           fill=RED, anchor="mm")

    # hidden rows
    hidden = [
        "  [40]  Fort Mason",
        "  ...",
        "  [420] Golden Gate Bridge  ← HIDDEN",
        "  ...",
        "  [437] Stow Lake",
    ]
    for i, row in enumerate(hidden):
        y = cut_y + 10 + i * 22
        highlight = "HIDDEN" in row
        _box(d, list_x, y, list_w, 20,
             RED_BG if highlight else SUBTLE,
             RED if highlight else SUBTLE, radius=3)
        color = RED if highlight else "#888"
        d.text((list_x + 8, y + 3), row, font=f_code, fill=color)

    # right panel
    rx = 460
    _text(d, rx, list_y, "Tavily receives only first 40", f_label, RED)
    _text(d, rx, list_y + 24, "→ LLM never sees idx 40–437", f_small, RED)

    _box(d, rx, 130, 380, 60, RED_BG, RED)
    d.text((rx + 190, 160), "Golden Gate Bridge\n(index 420)", font=f_code, fill=RED, anchor="mm")

    d.line([(rx, 165), (rx + 380, 165)], fill=RED, width=2)
    d.text((rx + 190, 178), "biking recall = 0%  (bridge never classified)", font=f_small,
           fill=RED, anchor="mm")

    # fix box
    _box(d, rx, 230, 380, 100, GREEN_BG, GREEN)
    _text(d, rx + 12, 242, "Fix:", f_label, GREEN)
    _text(d, rx + 12, 264, "Remove [:40] — send all 438 names", f_code, WHITE)
    _text(d, rx + 12, 284, "→ Golden Gate Bridge at idx 420 reaches LLM", f_code, WHITE)
    _text(d, rx + 12, 304, "→ Classified as biking ✓", f_code, GREEN)

    img.save(f"{OUT_DIR}/eval_tavily_name_cap.png")
    print(f"  ✓ eval_tavily_name_cap.png")


# ────────────────────────────────────────────────────────────────────────────
# Diagram 4 — Slot scaling before/after
# ────────────────────────────────────────────────────────────────────────────
def _slot_scaling():
    img, d = _img(W, 480)
    f_title = _font(20)
    f_label = _font(14)
    f_small = _font(12)
    f_code  = _font(11)

    _text(d, W // 2, 22, "Fix ④ — Activity Slot Scaling", f_title, BLUE, anchor="mt")

    # inputs
    _text(d, W // 2, 60, "Input: activities=[hiking, kids], total_stops=5", f_label, WHITE, anchor="mm")

    col_w = 360
    left_x = 50
    right_x = W - col_w - 50

    # BEFORE
    _text(d, left_x + col_w // 2, 95, "BEFORE", f_label, RED, anchor="mm")
    before_rows = [
        (RED_BG,    RED,    "n_activity_slots = min(2, 3)  →  2"),
        (RED_BG,    RED,    "  hiking (44 candidates)  →  1 slot"),
        (RED_BG,    RED,    "  kids   ( 8 candidates)  →  1 slot"),
        (SUBTLE,    WHITE,  ""),
        (YELLOW_BG, YELLOW, "Budget used:  2 / 4  (2 wasted)"),
    ]
    for i, (fill, color, text) in enumerate(before_rows):
        y = 115 + i * 50
        _box(d, left_x, y, col_w, 42, fill, color)
        d.text((left_x + 8, y + 14), text, font=f_code, fill=color)

    # stops visual: 1 hiking, 1 kids, 3 scenic
    sy = 115 + len(before_rows) * 50 + 14
    _text(d, left_x + col_w // 2, sy, "Itinerary (5 stops):", f_small, WHITE, anchor="mm")
    stop_colors = [(RED, "hiking"), (RED, "kids"), (SUBTLE, "scenic"), (SUBTLE, "scenic"), (SUBTLE, "scenic")]
    for si, (sc, sl) in enumerate(stop_colors):
        sx = left_x + si * 68
        _box(d, sx, sy + 18, 62, 36, RED_BG if sc == RED else "#2a2a3e", sc, radius=6)
        d.text((sx + 31, sy + 36), sl, font=_font(10), fill=sc, anchor="mm")

    # AFTER
    _text(d, right_x + col_w // 2, 95, "AFTER", f_label, GREEN, anchor="mm")
    after_rows = [
        (GREEN_BG,  GREEN, "_slots_for_activity(44)  →  3  (≥11)"),
        (GREEN_BG,  GREEN, "_slots_for_activity( 8)  →  2  (≥4)"),
        (GREEN_BG,  GREEN, "proportional(budget=4):"),
        (GREEN_BG,  GREEN, "  hiking  →  2 slots,  kids  →  2 slots"),
        (GREEN_BG,  GREEN, "Budget used:  4 / 4  ✓"),
    ]
    for i, (fill, color, text) in enumerate(after_rows):
        y = 115 + i * 50
        _box(d, right_x, y, col_w, 42, fill, color)
        d.text((right_x + 8, y + 14), text, font=f_code, fill=color)

    sy = 115 + len(after_rows) * 50 + 14
    _text(d, right_x + col_w // 2, sy, "Itinerary (5 stops):", f_small, WHITE, anchor="mm")
    stop_colors2 = [(BLUE, "hiking"), (BLUE, "hiking"), (GREEN, "kids"), (GREEN, "kids"), (SUBTLE, "scenic")]
    for si, (sc, sl) in enumerate(stop_colors2):
        sx = right_x + si * 68
        fill = BLUE_BG if sc == BLUE else (GREEN_BG if sc == GREEN else "#2a2a3e")
        _box(d, sx, sy + 18, 62, 36, fill, sc, radius=6)
        d.text((sx + 31, sy + 36), sl, font=_font(10), fill=sc, anchor="mm")

    # divider
    d.line([(W // 2, 85), (W // 2, 455)], fill=SUBTLE, width=1)

    img.save(f"{OUT_DIR}/eval_slot_scaling.png")
    print(f"  ✓ eval_slot_scaling.png")


# ────────────────────────────────────────────────────────────────────────────
# Diagram 5 — ReAct loop before/after (Improvement 9)
# ────────────────────────────────────────────────────────────────────────────
def _react_loop_fix():
    img, d = _img(900, 520)
    f_title = _font(18)
    f_head  = _font(14)
    f_label = _font(12)
    f_small = _font(11)

    _text(d, 450, 18, "Improvement 9 — Eliminating Redundant ReAct Tool Calls", f_title, BLUE, anchor="mt")

    # ── BEFORE (left column) ──────────────────────────────────────────────
    col_l = 40
    _text(d, col_l, 52, "BEFORE  (12 iterations, hit cap, never stopped)", f_head, RED)

    before_rows = [
        ("iter 0", "select_pois_for_day", "1.6s",  True,  "2.3s think"),
        ("iter 1", "rate_pois",           "13.6s", True,  "5.8s think"),
        ("iter 2", "estimate_visit_dur.", "0.0s",  False, "7.5s think  ← WASTED"),
        ("iter 3", "estimate_visit_dur.", "0.0s",  False, "2.2s think  ← WASTED"),
        ("iter 4", "enrich_poi_details",  "0.0s",  False, "1.2s think  ← WASTED"),
        ("iter 5", "estimate_visit_dur.", "0.0s",  False, "1.3s think  ← WASTED"),
        ("iter 6", "estimate_visit_dur.", "0.0s",  False, "1.1s think  ← WASTED"),
        ("iter 7", "estimate_visit_dur.", "0.0s",  False, "2.5s think  ← WASTED"),
        ("iter 8", "enrich_poi_details",  "1.6s",  False, "4.9s think  ← WASTED"),
        ("iter 9", "estimate_visit_dur.", "0.0s",  False, "2.1s think  ← WASTED"),
        ("iter 10","enrich_poi_details",  "2.5s",  False, "5.0s think  ← WASTED"),
        ("iter 11","estimate_visit_dur.", "0.0s",  False, "3.7s think  ← WASTED"),
    ]

    row_h = 30
    y0 = 76
    for i, (it, tool, elapsed, useful, note) in enumerate(before_rows):
        y = y0 + i * row_h
        fill = GREEN_BG if useful else RED_BG
        outline = GREEN if useful else RED
        _box(d, col_l, y, 390, row_h - 3, fill, outline, radius=4)
        d.text((col_l + 6,  y + 9), it,      font=f_small, fill=SUBTLE, anchor="la")
        d.text((col_l + 58, y + 9), tool,    font=f_small, fill=WHITE,  anchor="la")
        d.text((col_l + 230, y + 9), elapsed, font=f_small, fill=GREEN if useful else YELLOW, anchor="la")
        d.text((col_l + 278, y + 9), note,   font=f_small, fill=GREEN if useful else RED,    anchor="la")

    # total label
    ty = y0 + len(before_rows) * row_h + 4
    _box(d, col_l, ty, 390, 26, "#2a1a1e", RED, radius=4)
    d.text((col_l + 195, ty + 13), "Discover POIs step: ~38s  |  Total run: ~65s", font=f_small, fill=RED, anchor="mm")

    # ── divider ──────────────────────────────────────────────────────────
    d.line([(455, 50), (455, 490)], fill=SUBTLE, width=1)

    # ── AFTER (right column) ─────────────────────────────────────────────
    col_r = 470
    _text(d, col_r, 52, "AFTER  (2–3 iterations, stops naturally)", f_head, GREEN)

    after_rows = [
        ("iter 0", "select_pois_for_day", "1.6s",  True,  "~2s think"),
        ("iter 1", "rate_pois + desc +",  "~10s",  True,  "~5s think"),
        ("       ", "  visit_duration_min","(pre-computed)", True, ""),
        ("iter 2", "(no tool calls)",      "—",     True,  "~3s think → STOP"),
    ]

    for i, (it, tool, elapsed, useful, note) in enumerate(after_rows):
        y = y0 + i * row_h
        fill = GREEN_BG
        outline = GREEN
        _box(d, col_r, y, 390, row_h - 3, fill, outline, radius=4)
        d.text((col_r + 6,  y + 9), it,      font=f_small, fill=SUBTLE, anchor="la")
        d.text((col_r + 58, y + 9), tool,    font=f_small, fill=WHITE,  anchor="la")
        d.text((col_r + 240, y + 9), elapsed, font=f_small, fill=GREEN, anchor="la")
        d.text((col_r + 310, y + 9), note,   font=f_small, fill=GREEN,  anchor="la")

    # what changed box
    cx_y = y0 + len(after_rows) * row_h + 16
    _box(d, col_r, cx_y, 390, 110, BLUE_BG, BLUE, radius=6)
    changes = [
        "What changed:",
        "• rate_pois now returns visit_duration_min",
        "  (dict lookup, same _VISIT_MINUTES table)",
        "• rate_pois already returned description +",
        "  image_url via dataclasses.asdict(poi)",
        "• Prompt: 'Do NOT call enrich_poi_details",
        "  or estimate_visit_duration'",
    ]
    for j, line in enumerate(changes):
        col = BLUE if j == 0 else WHITE
        d.text((col_r + 10, cx_y + 8 + j * 15), line, font=f_small, fill=col, anchor="la")

    # after total label
    at_y = ty
    _box(d, col_r, at_y, 390, 26, "#1a3a26", GREEN, radius=4)
    d.text((col_r + 195, at_y + 13), "Discover POIs step: ~5s  |  Total run: ~30s", font=f_small, fill=GREEN, anchor="mm")

    # ── savings callout ──────────────────────────────────────────────────
    s_y = ty + 34
    _box(d, col_l, s_y, 840, 32, YELLOW_BG, YELLOW, radius=6)
    d.text((450 + 40, s_y + 16),
           "Savings: ~35s LLM overhead eliminated  |  38s → 5s Discover  |  65s → 30s total",
           font=f_head, fill=YELLOW, anchor="mm")

    img.save(f"{OUT_DIR}/eval_react_loop_fix.png")
    print(f"  ✓ eval_react_loop_fix.png")


if __name__ == "__main__":
    print(f"Writing diagrams to {OUT_DIR}/")
    _pipeline()
    _subtype_fix()
    _tavily_cap()
    _slot_scaling()
    _react_loop_fix()
    print("Done.")
