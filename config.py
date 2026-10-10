import os
from urllib.parse import quote_plus

BASE = os.path.abspath(os.path.dirname(__file__))

# Load variables from a .env file (if python-dotenv is installed and the file exists).
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE, ".env"))
except ImportError:
    pass


def build_database_uri():
    """Pick the database from the environment.

    Priority:
      1. DATABASE_URL                      (full SQLAlchemy URL, used as-is)
      2. DB_HOST / DB_USER / DB_NAME ...   (MySQL, URL is built for you)
      3. Local SQLite file                 (zero-setup default)
    """
    url = os.environ.get("DATABASE_URL")
    if url:
        # Some hosts hand out "mysql://"; SQLAlchemy needs the PyMySQL driver name.
        if url.startswith("mysql://"):
            url = url.replace("mysql://", "mysql+pymysql://", 1)
        return url

    host = os.environ.get("DB_HOST")
    if host:
        user = quote_plus(os.environ.get("DB_USER", "root"))
        password = quote_plus(os.environ.get("DB_PASSWORD", ""))  # handles @ : / in passwords
        port = os.environ.get("DB_PORT", "3306")
        name = os.environ.get("DB_NAME", "civicsense")
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}?charset=utf8mb4"

    return "sqlite:///" + os.path.join(BASE, "civicsense.db")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-me")
    SQLALCHEMY_DATABASE_URI = build_database_uri()
    # Keeps MySQL connections healthy (avoids "MySQL server has gone away").
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(BASE, "static", "uploads")
    MAX_CONTENT_LENGTH = 32 * 1024 * 1024
    IMAGE_EXT = {"png", "jpg", "jpeg", "webp"}
    VIDEO_EXT = {"mp4", "mov", "avi", "webm"}
    # Put your trained YOLO weights here (class names must match ai.CATEGORIES keys).
    YOLO_WEIGHTS = os.environ.get("YOLO_WEIGHTS", os.path.join(BASE, "weights", "civic_yolo.pt"))
