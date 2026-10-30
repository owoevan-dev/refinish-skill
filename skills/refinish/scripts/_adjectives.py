"""Words people use about a finish, and what each changes in a style file, one step at a time.

Each entry: the words it answers to (English, Chinese, Japanese; matched without case, a word anywhere in the
request), the changes per engine, and the measured number that should move (references/replicating-a-style.md), so a
change can be checked instead of guessed.

A change is one of:
  ("add", path, step, lo, hi)     the number at path raised by step, held within lo..hi (missing: from DEFAULTS)
  ("mul", path, factor, lo, hi)   multiplied
  ("set", path, value)            set outright
  ("post", layer)                 a post layer added, or the one of the same op replaced
  ("unpost", op)                  the post layers of that op taken out
A path is dotted: "shading.soft", "palette.chroma", "lines.outline.width".
"""

DEFAULTS = {                                     # a key's value when the style does not set it (style-format.md)
    "shading.soft": 0.0, "shading.harden": 0.85, "shading.tones": 2, "shading.tint_amount": 0.0,
    "palette.chroma": 1.0, "palette.contrast": 1.0, "palette.lift": 0.0,
    "lines.grow": 0.0, "lines.cut": 0.0, "lines.strength": 1.0, "lines.jitter": 0.0,
    "lines.keep.min_area": 6.67, "lines.keep.min_area_drawn": 0.67, "lines.outline.width": 1.0,
    "lines.trace.dark": 0.45,
    "touches.blush.alpha": 0.0, "texture.grain": 0.0,
    "deai.flatten": 0.55, "deai.chroma": 1.0, "deai.smooth": 0.8, "deai.outline": 0.0, "deai.line_dark": 0.85,
    "paint.texture.grain": 0.0,
}

ADJECTIVES = {
    "softer_shadows": {
        "words": ["softer shadows", "soft shading", "softer shading", "gentler shadows", "柔和的陰影", "陰影柔",
                  "陰影軟", "やわらかい影", "影を柔らかく"],
        "cel": [("add", "shading.soft", 0.5, 0.0, 3.0), ("add", "shading.harden", -0.05, 0.6, 1.0)],
        "deai": [("add", "deai.flatten", -0.08, 0.3, 0.95)],
        "measure": "edge_softness_median up"},
    "harder_shadows": {
        "words": ["harder shadows", "crisper shadows", "hard shadows", "sharp shadows", "陰影硬", "硬邊",
                  "パキッとした影", "影をくっきり"],
        "cel": [("add", "shading.soft", -0.5, 0.0, 3.0), ("add", "shading.harden", 0.05, 0.6, 1.0)],
        "deai": [("add", "deai.flatten", 0.08, 0.3, 0.95)],
        "measure": "edge_softness_median down, flatness_median up"},
    "flatter": {
        "words": ["flatter", "more flat", "flat colour", "flat color", "平塗", "更平", "フラット", "ベタ塗り"],
        "cel": [("add", "shading.harden", 0.05, 0.6, 1.0), ("set", "shading.tones", 2)],
        "deai": [("add", "deai.flatten", 0.1, 0.3, 0.95)],
        "measure": "flatness_median up"},
    "more_shading": {
        "words": ["more shading", "richer shading", "second shadow", "deeper shading", "三階影", "二影", "影を増やす",
                  "厚塗り感"],
        "cel": [("set", "shading.tones", 3)],
        "deai": [("set", "deai.tones", 3)],
        "measure": "by eye: a deeper tone under the chin and in the folds"},
    "thicker_lines": {
        "words": ["thicker lines", "bolder lines", "heavier lines", "粗線", "線粗", "線條粗", "線を太く",
                  "太い線"],
        "cel": [("add", "lines.grow", 0.2, 0.0, 1.2)],
        "deai": [("set", "deai.lines", "crisp"), ("add", "deai.outline", 0.3, 0.0, 2.0)],
        "measure": "line_width up"},
    "thinner_lines": {
        "words": ["thinner lines", "finer lines", "lighter touch", "細線", "線細", "線條細", "線を細く", "細い線"],
        "cel": [("add", "lines.grow", -0.2, 0.0, 1.2), ("add", "lines.cut", 0.03, 0.0, 0.25)],
        "measure": "line_width down"},
    "coloured_lines": {
        "words": ["coloured lines", "colored lines", "lighter lines", "softer lines", "彩色線", "色線", "線淡",
                  "色トレス", "線を色に"],
        "cel": [("set", "lines.colour", "trace"), ("add", "lines.trace.dark", 0.05, 0.3, 0.8)],
        "deai": [("add", "deai.line_dark", 0.08, 0.4, 1.0)],
        "measure": "line_to_fill up, line_hue_match near 1"},
    "black_lines": {
        "words": ["black lines", "darker lines", "ink lines", "黑線", "線深", "墨線", "主線を黒く", "黒い線"],
        "cel": [("set", "lines.colour", "ink"), ("set", "lines.ink.ink", [12, 2, 2])],
        "deai": [("set", "deai.lines", "crisp"), ("add", "deai.line_dark", -0.08, 0.4, 1.0)],
        "measure": "line_to_fill down"},
    "fewer_lines": {
        "words": ["fewer lines", "cleaner lines", "simpler lines", "less detail", "線少", "簡潔", "線を減らす"],
        "cel": [("add", "lines.keep.min_area", 2.0, 0.5, 40.0), ("add", "lines.keep.min_area_drawn", 0.5, 0.2, 10.0),
                ("add", "lines.cut", 0.03, 0.0, 0.25)],
        "measure": "line_density down"},
    "more_lines": {
        "words": ["more lines", "keep the details", "more detail", "線多", "保留細節", "細部を残す"],
        "cel": [("add", "lines.keep.min_area", -2.0, 0.5, 40.0), ("add", "lines.keep.min_area_drawn", -0.3, 0.2, 10.0),
                ("add", "lines.cut", -0.03, 0.0, 0.25)],
        "deai": [("add", "deai.flatten", -0.08, 0.3, 0.95)],
        "measure": "line_density up"},
    "outline": {
        "words": ["outline", "closed outline", "outlined", "外框", "外輪廓線", "主線で囲む", "アウトライン"],
        "cel": [("add", "lines.outline.width", 0.3, 0.6, 2.5)],
        "deai": [("add", "deai.outline", 0.3, 0.0, 2.0)],
        "measure": "outline coverage up (measure_style.py: outline)"},
    "more_vivid": {
        "words": ["more vivid", "more saturated", "brighter colours", "brighter colors", "punchier colours", "鮮豔",
                  "飽和", "顏色鮮", "彩度を上げる", "鮮やか"],
        "cel": [("mul", "palette.chroma", 1.1, 0.5, 1.6)],
        "deai": [("mul", "deai.chroma", 1.05, 0.8, 1.2)],
        "measure": "chroma.median up"},
    "muted": {
        "words": ["muted", "less saturated", "desaturated", "dull", "灰一點", "灰灰的", "低彩", "顏色淡", "くすんだ",
                  "彩度を下げる"],
        "cel": [("mul", "palette.chroma", 0.9, 0.4, 1.6)],
        "deai": [("mul", "deai.chroma", 0.95, 0.8, 1.2)],
        "measure": "chroma.median down"},
    "pastel": {
        "words": ["pastel", "airy", "high-key", "high key", "light and airy", "粉彩", "透明感", "明亮", "淡彩",
                  "パステル", "ハイキー"],
        "cel": [("add", "palette.lift", 4.0, -12.0, 14.0), ("mul", "palette.contrast", 0.94, 0.7, 1.3),
                ("mul", "palette.chroma", 0.95, 0.4, 1.6)],
        "measure": "value range down, median L up"},
    "moody": {
        "words": ["moody", "darker", "low-key", "low key", "heavier", "暗沉", "陰鬱", "厚重", "暗い", "ローキー"],
        "cel": [("add", "palette.lift", -4.0, -12.0, 14.0), ("mul", "palette.contrast", 1.06, 0.7, 1.3)],
        "measure": "median L down"},
    "more_contrast": {
        "words": ["more contrast", "punchier", "contrasty", "對比強", "對比高", "コントラスト強", "メリハリ"],
        "cel": [("mul", "palette.contrast", 1.08, 0.7, 1.4)],
        "measure": "value range up"},
    "less_contrast": {
        "words": ["less contrast", "softer contrast", "對比弱", "對比低", "コントラスト弱"],
        "cel": [("mul", "palette.contrast", 0.93, 0.6, 1.4)],
        "measure": "value range down"},
    "cooler_shadows": {
        "words": ["cooler shadows", "blue shadows", "cool shadows", "冷色影", "藍色陰影", "影を青く", "寒色の影"],
        "cel": [("set", "shading.tint", [0.88, 0.9, 1.0]), ("add", "shading.tint_amount", 0.15, 0.0, 0.8)],
        "measure": "shadow_shift b down"},
    "warmer_shadows": {
        "words": ["warmer shadows", "warm shadows", "red shadows", "暖色影", "紅色陰影", "影を赤く", "暖色の影"],
        "cel": [("set", "shading.tint", [1.0, 0.9, 0.86]), ("add", "shading.tint_amount", 0.15, 0.0, 0.8)],
        "measure": "shadow_shift a and b up"},
    "grainier": {
        "words": ["grainier", "film grain", "grain", "grainy", "顆粒", "粒子感", "噪點感", "ざらつき", "粒子"],
        "cel": [("add", "texture.grain", 0.004, 0.0, 0.03)],
        "paint": [("add", "texture.grain", 0.004, 0.0, 0.03)],
        "measure": "texture up"},
    "cleaner": {
        "words": ["cleaner", "no grain", "smoother", "乾淨", "去顆粒", "滑順", "クリーン"],
        "cel": [("set", "texture.grain", 0.0), ("unpost", "grain")],
        "deai": [("add", "deai.flatten", 0.05, 0.3, 0.95)],
        "measure": "texture down"},
    "retro": {
        "words": ["retro", "film look", "vintage", "old anime", "復古", "膠片", "懷舊", "フィルム", "レトロ"],
        "cel": [("post", {"op": "soften", "radius": 0.35, "amount": 0.6}),
                ("post", {"op": "halation", "threshold": 0.82, "radius": 5.0, "amount": 0.15}),
                ("post", {"op": "curve", "lift": [0.035, 0.03, 0.045], "gain": [0.97, 0.96, 0.93]}),
                ("post", {"op": "grain", "amount": 0.007, "size": 0.5}), ("add", "lines.jitter", 0.15, 0.0, 0.5)],
        "measure": "by eye: lifted blacks, a soft glow, grain"},
    "more_blush": {
        "words": ["more blush", "rosier", "rosy cheeks", "腮紅", "紅潤", "頬を赤く", "チーク"],
        "cel": [("add", "touches.blush.alpha", 0.08, 0.0, 0.45)],
        "measure": "by eye"},
    "hand_traced": {
        "words": ["hand-traced", "hand traced", "wobbly lines", "hand-drawn lines", "手繪線", "手描き", "線の揺れ"],
        "cel": [("add", "lines.jitter", 0.15, 0.0, 0.5)],
        "measure": "by eye: the line wanders off the drawing by a fraction of its width"},
    "sharper": {
        "words": ["sharper", "crisper", "crisp", "銳利", "清晰", "くっきり", "シャープ"],
        "cel": [("unpost", "soften"), ("add", "shading.soft", -0.3, 0.0, 3.0)],
        "measure": "edge_softness_median down"},
    "glow": {
        "words": ["glow", "bloom", "halation", "光暈", "發光", "柔光", "グロー", "にじみ"],
        "cel": [("post", {"op": "halation", "threshold": 0.8, "radius": 6.0, "amount": 0.25})],
        "measure": "by eye: a warm glow round the brightest areas"},
}


def match(text):
    """The entries a request names: every entry one of whose words appears in it (case ignored), longest words first,
    so "softer shadows" is not also read as "shadows"."""
    t = text.lower()
    hits, taken = [], []
    pairs = sorted(((w.lower(), k) for k, e in ADJECTIVES.items() for w in e["words"]), key=lambda p: -len(p[0]))
    for w, k in pairs:
        i = t.find(w)
        while i >= 0:
            span = (i, i + len(w))
            if not any(s < span[1] and span[0] < e for s, e in taken):
                taken.append(span)
                if k not in hits:
                    hits.append(k)
                break
            i = t.find(w, i + 1)
    return hits
