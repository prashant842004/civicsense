import math
import os
import uuid
from functools import wraps

from flask import abort, current_app
from flask_login import current_user
from PIL import Image
from werkzeug.utils import secure_filename

from models import ComplaintEvent, Notification, User, db


def role_required(*roles):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **k):
            if not current_user.is_authenticated:
                return current_app.login_manager.unauthorized()
            if current_user.role not in roles:
                abort(403)
            return f(*a, **k)
        return wrapper
    return deco


def save_upload(file, allow_video=True):
    """Validate and store an uploaded photo/video. Returns (filename, media_type)."""
    if not file or not file.filename:
        raise ValueError("No file selected")
    ext = secure_filename(file.filename).rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    cfg = current_app.config
    if ext in cfg["IMAGE_EXT"]:
        kind = "image"
    elif allow_video and ext in cfg["VIDEO_EXT"]:
        kind = "video"
    else:
        raise ValueError("Unsupported file type. Use " + ", ".join(
            sorted(cfg["IMAGE_EXT"] | (cfg["VIDEO_EXT"] if allow_video else set()))))
    name = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(cfg["UPLOAD_FOLDER"], name)
    file.save(path)
    if kind == "image":
        try:
            with Image.open(path) as im:
                im.verify()
        except Exception:
            os.remove(path)
            raise ValueError("That file is not a valid image")
    return name, kind


def upload_path(name):
    return os.path.join(current_app.config["UPLOAD_FOLDER"], name)


def add_event(complaint, text):
    complaint.events.append(ComplaintEvent(text=text))


def notify(user_id, message, link=None):
    db.session.add(Notification(user_id=user_id, message=message[:255], link=link))


def notify_admins(message, link=None):
    for (uid,) in db.session.query(User.id).filter_by(role="admin"):
        notify(uid, message, link)


def haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def parse_coords(lat, lng):
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        raise ValueError("Please pick the issue location on the map")
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValueError("Location is out of range")
    return lat, lng
