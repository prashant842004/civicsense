"""AI module: issue detection, priority, routing, resolution check.

Two engines:
  1. YOLO (ultralytics) -- used automatically when trained weights exist at
     Config.YOLO_WEIGHTS and ultralytics is installed. Class names must be the
     keys of CATEGORIES (pothole, garbage, ...).
  2. Rule-based fallback -- OpenCV image statistics + the category the citizen
     picked + keywords in the description. This is NOT a trained detector; it
     keeps the system usable until you train/add YOLO weights.
"""
import os
import tempfile

try:
    import cv2
    import numpy as np
except Exception:  # pragma: no cover
    cv2 = None
    np = None

# key: (label, department, volunteer rule, base level 0=Low 1=Medium 2=High)
# volunteer rule: "always" | "if_low" | "never"
CATEGORIES = {
    "pothole": ("Pothole", "Roads & Traffic", "never", 1),
    "damaged_road": ("Damaged road", "Roads & Traffic", "never", 1),
    "garbage": ("Garbage accumulation", "Sanitation", "if_low", 0),
    "overflowing_drain": ("Overflowing drain", "Drainage & Sewerage", "never", 1),
    "dirty_toilet": ("Dirty public toilet", "Public Toilets", "never", 1),
    "broken_streetlight": ("Broken streetlight", "Electrical", "never", 1),
    "illegal_dumping": ("Illegal dumping", "Sanitation", "if_low", 0),
    "litter": ("Litter / street cleaning", "Sanitation", "always", 0),
    "park_cleaning": ("Park cleaning", "Parks & Gardens", "always", 0),
    "other": ("Other", "General Administration", "never", 0),
}
DEPARTMENTS = sorted({v[1] for v in CATEGORIES.values()})
LEVELS = ["Low", "Medium", "High"]

KEYWORDS = {
    "pothole": ["pothole", "pit", "crater", "gaddha", "khadda"],
    "damaged_road": ["road damage", "damaged road", "broken road", "cracked road", "crack"],
    "garbage": ["garbage", "trash", "waste", "kachra", "dustbin", "dump"],
    "overflowing_drain": ["drain", "sewage", "sewer", "overflow", "naali", "gutter"],
    "dirty_toilet": ["toilet", "urinal", "washroom", "restroom"],
    "broken_streetlight": ["streetlight", "street light", "lamp", "light not working", "dark street"],
    "illegal_dumping": ["illegal dump", "dumping", "debris", "construction waste"],
    "litter": ["litter", "plastic", "wrapper", "cleanup", "cleaning"],
    "park_cleaning": ["park", "garden", "playground"],
}
URGENT_WORDS = ["urgent", "accident", "danger", "dangerous", "child", "children", "school",
                "hospital", "flood", "injury", "injured", "open manhole", "electric shock", "fire"]

_yolo = {"model": None, "path": None}


def label(key):
    return CATEGORIES.get(key, CATEGORIES["other"])[0]


def category_choices():
    return [(k, v[0]) for k, v in CATEGORIES.items()]


def route_complaint(category, priority):
    """Dual routing: community-manageable issues go to volunteers, the rest to the municipal dept."""
    _, dept, rule, _ = CATEGORIES.get(category, CATEGORIES["other"])
    if rule == "always" or (rule == "if_low" and priority == "Low"):
        return "volunteer", "Community Volunteers"
    return "municipal", dept


# ---------------------------------------------------------------- media helpers
def frame_from_video(path):
    """Return the middle frame of a video as a BGR array (or None)."""
    if cv2 is None:
        return None
    cap = cv2.VideoCapture(path)
    try:
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if n > 1:
            cap.set(cv2.CAP_PROP_POS_FRAMES, n // 2)
        ok, frame = cap.read()
        return frame if ok else None
    finally:
        cap.release()


def load_bgr(path, media_type):
    if cv2 is None:
        return None
    return frame_from_video(path) if media_type == "video" else cv2.imread(path)


# ---------------------------------------------------------------- analysis
def _yolo_model(weights):
    if not weights or not os.path.exists(weights):
        return None
    if _yolo["path"] != weights:
        try:
            from ultralytics import YOLO
            _yolo.update(model=YOLO(weights), path=weights)
        except Exception:
            _yolo.update(model=None, path=weights)
    return _yolo["model"]


def _analyze_yolo(model, img):
    res = model.predict(img, verbose=False)[0]
    if res.boxes is None or len(res.boxes) == 0:
        return None
    h, w = img.shape[:2]
    best, best_conf = None, 0.0
    area_by_cls = {}
    for b in res.boxes:
        name = res.names[int(b.cls)]
        x1, y1, x2, y2 = b.xyxy[0].tolist()
        area_by_cls[name] = area_by_cls.get(name, 0) + (x2 - x1) * (y2 - y1) / (w * h)
        if float(b.conf) > best_conf:
            best, best_conf = name, float(b.conf)
    if best not in CATEGORIES:
        return None
    area = area_by_cls[best]
    bump = 2 if area > 0.25 else 1 if area > 0.08 else 0
    return best, best_conf, bump


def _image_bump(img):
    """Crude severity cue: lots of texture/dark clutter -> bigger problem (0 or 1)."""
    g = cv2.cvtColor(cv2.resize(img, (256, 256)), cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(g, 80, 160).mean() / 255.0
    dark = float((g < 60).mean())
    return 1 if (edges > 0.12 or dark > 0.35) else 0


def _keyword_category(text):
    text = text.lower()
    scores = {k: sum(w in text for w in ws) for k, ws in KEYWORDS.items()}
    k = max(scores, key=scores.get)
    return k if scores[k] else None


def analyze(path, media_type, hint, description, weights=None):
    """Return dict(category, priority, confidence, source, note)."""
    text = description or ""
    img = load_bgr(path, media_type) if path else None
    model = _yolo_model(weights)
    urgent = any(w in text.lower() for w in URGENT_WORDS)

    if model is not None and img is not None:
        out = _analyze_yolo(model, img)
        if out:
            cat, conf, bump = out
            level = min(2, CATEGORIES[cat][3] + bump + (1 if urgent else 0))
            return dict(category=cat, priority=LEVELS[level], confidence=round(conf, 2),
                        source="yolo", note="Detected by trained YOLO model")

    cat = hint if hint in CATEGORIES else _keyword_category(text) or "other"
    bump = _image_bump(img) if img is not None else 0
    level = min(2, CATEGORIES[cat][3] + bump + (1 if urgent else 0))
    why = "citizen's selection" if hint in CATEGORIES else "description keywords" if cat != "other" else "no clear signal"
    note = f"Rule-based (no trained model loaded): category from {why}"
    if urgent:
        note += "; urgent wording raised priority"
    return dict(category=cat, priority=LEVELS[level], confidence=None, source="rule-based", note=note)


# ---------------------------------------------------------------- verification
def compare_before_after(before_path, before_type, after_path):
    """Heuristic before/after check. Returns (score 0-1, note). Higher = scene changed more."""
    if cv2 is None:
        return None, "OpenCV not available"
    a, b = load_bgr(before_path, before_type), cv2.imread(after_path)
    if a is None or b is None:
        return None, "Could not read one of the images"
    size = (256, 256)
    ga = cv2.cvtColor(cv2.resize(a, size), cv2.COLOR_BGR2GRAY)
    gb = cv2.cvtColor(cv2.resize(b, size), cv2.COLOR_BGR2GRAY)
    diff = float(np.abs(ga.astype(int) - gb.astype(int)).mean()) / 255.0
    ha = cv2.calcHist([ga], [0], None, [32], [0, 256])
    hb = cv2.calcHist([gb], [0], None, [32], [0, 256])
    corr = float(cv2.compareHist(ha, hb, cv2.HISTCMP_CORREL))
    score = round(min(1.0, diff * 3 + (1 - max(corr, 0)) * 0.5), 2)
    note = ("Scene looks changed - consistent with work being done" if score >= 0.15
            else "Photos look nearly identical - check manually")
    return score, note
