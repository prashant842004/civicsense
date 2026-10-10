"""Check / set up the database connection.

    python db_check.py            test connection, create the MySQL database if missing, create tables
    python db_check.py --test     only test the connection
"""
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from config import Config


def safe(url):
    return url.render_as_string(hide_password=True)


def ensure_mysql_database(url):
    """Connect to the MySQL server (no database selected) and create the DB if needed."""
    server_url = url.set(database=None)
    engine = create_engine(server_url)
    with engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{url.database}` "
                          "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
        conn.commit()
    engine.dispose()


def main():
    only_test = "--test" in sys.argv
    url = make_url(Config.SQLALCHEMY_DATABASE_URI)
    print(f"Database : {safe(url)}")

    try:
        if url.get_backend_name() == "mysql" and not only_test:
            ensure_mysql_database(url)
            print(f"Database '{url.database}' is ready.")
        engine = create_engine(url)
        with engine.connect() as conn:
            version = conn.execute(text("SELECT 1")).scalar()
        print("Connection OK" if version == 1 else "Unexpected result")
    except OperationalError as e:
        print("\nCould not connect to the database.")
        print(f"Reason: {e.orig}")
        print("\nChecklist:\n"
              "  - Is MySQL running?\n"
              "  - Are DB_HOST / DB_USER / DB_PASSWORD / DB_NAME correct in .env?\n"
              "  - Is PyMySQL installed?  pip install -r requirements.txt")
        sys.exit(1)

    if not only_test:
        from app import create_app
        from models import db
        app = create_app()
        with app.app_context():
            db.create_all()
            print("Tables:", ", ".join(sorted(db.metadata.tables)))
        print("Done. Next: python seed.py && python app.py")


if __name__ == "__main__":
    main()
