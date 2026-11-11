"""
inspect_digikam_db.py - Read-only look inside your digiKam database.

    python tools/inspect_digikam_db.py            # pick-label IDs + status/label counts
    python tools/inspect_digikam_db.py --tags     # also list EVERY tag (includes people names!)
    python tools/inspect_digikam_db.py --schema   # also print a few table schemas

Use it to confirm the Pick Label tag IDs to put in config.py
(TAG_NONE / TAG_REJECTED / TAG_PENDING / TAG_ACCEPTED). The database is
opened read-only, so it is safe to run while digiKam is open.

Privacy note: the output of --tags can contain people's names. Do not paste
it into public issues without checking it.
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", action="store_true", help="list all tags")
    ap.add_argument("--schema", action="store_true", help="print table schemas")
    ap.add_argument("--db", help="database path (default: DIGIKAM_DB from config.py)")
    args = ap.parse_args()

    db_path = Path(args.db) if args.db else Path(common.cfg("DIGIKAM_DB", ""))
    if not db_path.exists():
        sys.exit("Database not found: " + str(db_path))
    conn = sqlite3.connect("file:" + db_path.as_posix() + "?mode=ro", uri=True)
    cur = conn.cursor()

    print("Pick Label tags (use these IDs in config.py):")
    cur.execute("SELECT id, name FROM Tags WHERE name LIKE 'Pick Label%' ORDER BY id")
    rows = cur.fetchall()
    for tag_id, name in rows:
        n = cur.execute("SELECT COUNT(*) FROM ImageTags WHERE tagid = ?", (tag_id,)).fetchone()[0]
        print("  id=" + str(tag_id) + "  " + name + "  (" + str(n) + " images)")
    if not rows:
        print("  none found - run with --tags and look for the pick/reject labels")

    print("")
    print("Images.status counts (1 = live):")
    for status, n in cur.execute("SELECT status, COUNT(*) FROM Images GROUP BY status"):
        print("  status=" + str(status) + "  count=" + str(n))

    if args.tags:
        print("")
        print("All tags:")
        for tag_id, pid, name in cur.execute("SELECT id, pid, name FROM Tags ORDER BY pid, name"):
            print("  id=" + str(tag_id) + " pid=" + str(pid) + " " + str(name))

    if args.schema:
        for table in ("Images", "ImageTags", "Albums", "ImageProperties", "ImageTagProperties"):
            print("")
            print("Schema of " + table + ":")
            for col in cur.execute("PRAGMA table_info(" + table + ")"):
                print("  " + str(col))
    conn.close()


if __name__ == "__main__":
    main()
