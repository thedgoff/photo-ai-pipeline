"""
blur_review.py - Second opinion on photos digiKam marked "Rejected".

Reads digiKam's database, sends every Rejected photo to Claude, and moves the
ones that look fine from Rejected to Pending. Every photo that was reviewed
gets the XMP tag "Claude Reviewed" so you can see what has been assessed.

    python blur_review.py --dry-run --limit 20   # cheap trial, changes nothing
    python blur_review.py                        # the real run

SAFETY
  * Close digiKam first, reopen it afterwards.
  * The database is backed up to logs/backups/ before any change.
  * Nothing is ever deleted by this script. Missing/unclear answers keep the
    photo Rejected.
"""
import argparse
import sys
from datetime import datetime

import common
import digikam_db as db

INSTRUCTIONS = (
    "I'm going to show you photos that were flagged as potentially poor quality. "
    "For each photo, assess whether it should be KEPT or REJECTED. "
    "Reasons to REJECT: severely blurry/out of focus, extremely dark/underexposed, "
    "heavily overexposed, duplicate of another photo, completely obscured subject. "
    "Reasons to KEEP: slightly soft but recognizable, motion blur that adds effect, "
    "dark but subject visible, candid/imperfect but meaningful moment. "
    "Be lenient - only reject photos that are truly unusable. "
    "Return a JSON object with the image ID as key and 'keep' or 'reject' as value. "
    'Example: {"123": "keep", "456": "reject"}. '
    "Return ONLY valid JSON, no explanation, no markdown."
)


def main():
    ap = argparse.ArgumentParser(description="Re-check Rejected photos with Claude.")
    ap.add_argument("--dry-run", action="store_true", help="report only; change nothing")
    ap.add_argument("--limit", type=int, help="review at most N photos")
    args = ap.parse_args()

    db_path = common.cfg("DIGIKAM_DB")
    root = common.pictures_root()
    tag_rejected = common.cfg("TAG_REJECTED", 20)
    tag_pending = common.cfg("TAG_PENDING", 21)
    if not args.dry_run:
        common.check_exiftool()
    client = common.get_client()

    conn = db.open_db(db_path)
    rows = db.photos_with_label(conn, tag_rejected)
    photos, missing = [], 0
    for image_id, name, rel in rows:
        path = db.resolve_file(root, rel, name)
        if path.exists():
            photos.append((image_id, name, path))
        else:
            missing += 1
    if args.limit:
        photos = photos[:args.limit]
    print("Rejected in database: " + str(len(rows)) + "  | on disk: " + str(len(photos))
          + "  | missing: " + str(missing))
    if not photos:
        return

    batch_size = common.cfg("REVIEW_BATCH_SIZE", 5)
    verdicts = {}
    for i in range(0, len(photos), batch_size):
        batch = []
        for image_id, name, path in photos[i:i + batch_size]:
            try:
                batch.append((image_id, common.image_b64(path)))
            except Exception as exc:
                print("  SKIP " + name + ": " + str(exc))
        if not batch:
            continue
        print("  Batch " + str(i // batch_size + 1) + " of "
              + str((len(photos) + batch_size - 1) // batch_size))
        try:
            verdicts.update(common.assess_batch(client, batch, INSTRUCTIONS,
                                                valid={"keep", "reject"}, default="reject"))
        except Exception as exc:
            print("  WARNING batch failed (photos stay Rejected): " + str(exc))

    keep, reject = [], []
    for image_id, name, path in photos:
        if str(image_id) not in verdicts:
            continue  # never reviewed -> untouched
        (keep if verdicts[str(image_id)] == "keep" else reject).append((image_id, name, path))

    print("")
    print("Result: " + str(len(keep)) + " look fine -> Pending, " + str(len(reject)) + " stay Rejected")
    if args.dry_run:
        for _, name, _ in keep:
            print("  would move to Pending: " + name)
        return

    backup = db.backup_db(db_path, common.log_path("backups"))
    print("Database backed up to " + str(backup))
    for _, name, path in keep + reject:
        common.write_xmp_subject(path, ["Claude Reviewed"])
    for image_id, name, _ in keep:
        db.set_label(conn, image_id, tag_rejected, tag_pending)
        print("  Moved to Pending: " + name)
    conn.commit()
    conn.close()

    with open(common.log_path("blur_review_log.txt"), "a", encoding="utf-8") as log:
        log.write("\n=== " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " ===\n")
        log.write("Moved to Pending (" + str(len(keep)) + "):\n")
        for _, name, _ in keep:
            log.write("  " + name + "\n")
        log.write("Stayed Rejected (" + str(len(reject)) + ")\n")
    print("Done. Reopen digiKam to see the updated labels.")


if __name__ == "__main__":
    sys.exit(main())
