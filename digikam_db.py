"""
digikam_db.py - small helpers for reading/changing digiKam's SQLite database.

Facts this relies on (digiKam 8/9, verified on 9.0):
  * Pick Labels are stored as ordinary tags linked through the ImageTags table
    (None/Rejected/Pending/Accepted - IDs are configurable in config.py).
  * Images.status = 1 means a live (non-removed) image.
  * Albums.relativePath + Images.name gives the file path under the album root.

ALWAYS close digiKam before writing, and use backup_db() first.
"""
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

RELATED_TABLES = [
    "ImageTags", "ImageInformation", "ImageMetadata", "ImageComments",
    "ImageProperties", "ImageTagProperties", "ImagePositions",
    "ImageHistory", "ImageRelations",
]


def open_db(db_path):
    db_path = Path(db_path)
    if not db_path.exists():
        sys.exit("digiKam database not found: " + str(db_path) + "\nSet DIGIKAM_DB in config.py.")
    return sqlite3.connect(str(db_path), timeout=10)


def backup_db(db_path, backup_dir) -> Path:
    """Copy the database to backup_dir with a timestamp and return the copy."""
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / (Path(db_path).stem + "_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".db")
    shutil.copy2(str(db_path), str(dest))
    return dest


def photos_with_label(conn, tag_id):
    """Return [(image_id, name, relativePath)] for live images carrying tag_id."""
    cur = conn.execute(
        """
        SELECT i.id, i.name, a.relativePath
        FROM Images i
        JOIN ImageTags it ON i.id = it.imageid
        JOIN Albums a ON i.album = a.id
        WHERE it.tagid = ? AND i.status = 1
        """,
        (tag_id,),
    )
    return cur.fetchall()


def resolve_file(library_root, relative_path, name) -> Path:
    return Path(library_root) / (relative_path or "").lstrip("/") / name


def set_label(conn, image_id, old_tag_id, new_tag_id):
    """Swap a Pick Label. Caller commits."""
    conn.execute("DELETE FROM ImageTags WHERE imageid = ? AND tagid = ?",
                 (image_id, old_tag_id))
    conn.execute("INSERT OR IGNORE INTO ImageTags (imageid, tagid) VALUES (?, ?)",
                 (image_id, new_tag_id))


def remove_image(conn, image_id):
    """Remove an image from every related table, then from Images. Caller commits."""
    existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table in RELATED_TABLES:
        if table in existing:
            conn.execute("DELETE FROM " + table + " WHERE imageid = ?", (image_id,))
    conn.execute("DELETE FROM Images WHERE id = ?", (image_id,))
