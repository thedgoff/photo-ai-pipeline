"""
pending_review.py - Quality check of photos digiKam marks "Pending".

Claude gives each Pending photo one verdict:
  keep        fine -> stays Pending
  reject      blurry / very dark / washed out -> moved to Rejected
  screenshot  screen capture, phone UI, map, chat ... -> see below

Every reviewed photo gets the XMP tag "Claude Reviewed".

SCREENSHOTS
  Default (safe):  moved to Rejected and tagged "Screenshot" so you can
                   review and delete them yourself in digiKam.
  --delete-screenshots:  PERMANENTLY deletes the file from disk and removes
                   it from the digiKam database. No recycle bin. Use
                   --dry-run first and read the list.

    python pending_review.py --dry-run --limit 20
    python pending_review.py
    python pending_review.py --delete-screenshots

SAFETY: close digiKam first. The database is backed up to logs/backups/ before
any change. Missing/unclear answers keep the photo as it is.
"""
import argparse
import sys
from datetime import datetime

import common
import digikam_db as db

INSTRUCTIONS = (
    "I'm going to show you photos from a personal photo library. "
    "For each photo, assess its quality and type. Return one of three verdicts:\n"
    "- 'keep': Photo is fine as-is. Slightly imperfect photos of real moments should be kept.\n"
    "- 'reject': Photo is blurry/out of focus, very dark/underexposed, heavily washed "
    "out/overexposed, or otherwise clearly unusable as a personal memory.\n"
    "- 'screenshot': This is a screenshot, screen capture, phone UI, app interface, "
    "text message screenshot, map screenshot, or any image that is clearly not a real photo.\n\n"
    "Be lenient with 'keep' - only reject photos that are genuinely unusable. "
    "Be strict with 'screenshot' - if it looks like a screen capture of any kind, mark it.\n\n"
    "Return a JSON object with the image ID as key and verdict as value. "
    'Example: {"123": "keep", "456": "reject", "789": "screenshot"}. '
    "Return ONLY valid JSON, no explanation, no markdown."
)


def main():
    ap = argparse.ArgumentParser(description="Quality-check Pending photos with Claude.")
    ap.add_argument("--dry-run", action="store_true", help="report only; change nothing")
    ap.add_argument("--limit", type=int, help="review at most N photos")
    ap.add_argument("--delete-screenshots", action="store_true",
                    help="PERMANENTLY delete screenshots (default: move to Rejected)")
    args = ap.parse_args()

    db_path = common.cfg("DIGIKAM_DB")
    root = common.pictures_root()
    tag_rejected = common.cfg("TAG_REJECTED", 20)
    tag_pending = common.cfg("TAG_PENDING", 21)
    if not args.dry_run:
        common.check_exiftool()
    client = common.get_client()

    conn = db.open_db(db_path)
    rows = db.photos_with_label(conn, tag_pending)
    photos, missing = [], 0
    for image_id, name, rel in rows:
        path = db.resolve_file(root, rel, name)
        if path.exists():
            photos.append((image_id, name, path))
        else:
            missing += 1
    if args.limit:
        photos = photos[:args.limit]
    print("Pending in database: " + str(len(rows)) + "  | on disk: " + str(len(photos))
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
            verdicts.update(common.assess_batch(
                client, batch, INSTRUCTIONS,
                valid={"keep", "reject", "screenshot"}, default="keep"))
        except Exception as exc:
            print("  WARNING batch failed (photos left unchanged): " + str(exc))

    groups = {"keep": [], "reject": [], "screenshot": []}
    for item in photos:
        v = verdicts.get(str(item[0]))
        if v:  # photos from failed batches have no verdict -> untouched
            groups[v].append(item)

    print("")
    print("Result: keep=" + str(len(groups["keep"])) + "  reject=" + str(len(groups["reject"]))
          + "  screenshot=" + str(len(groups["screenshot"])))
    if args.dry_run:
        for label in ("reject", "screenshot"):
            for _, name, _ in groups[label]:
                print("  would " + label + ": " + name)
        return

    backup = db.backup_db(db_path, common.log_path("backups"))
    print("Database backed up to " + str(backup))

    for label in groups:
        for _, name, path in groups[label]:
            if label == "screenshot" and args.delete_screenshots:
                continue  # about to be deleted; no point tagging
            common.write_xmp_subject(path, ["Claude Reviewed"] +
                                     (["Screenshot"] if label == "screenshot" else []))

    for image_id, name, _ in groups["reject"]:
        db.set_label(conn, image_id, tag_pending, tag_rejected)
        print("  Moved to Rejected: " + name)

    deleted = []
    for image_id, name, path in groups["screenshot"]:
        if args.delete_screenshots:
            try:
                path.unlink()
                db.remove_image(conn, image_id)
                deleted.append(name)
                print("  DELETED screenshot: " + name)
            except OSError as exc:
                print("  ERROR deleting " + name + ": " + str(exc))
        else:
            db.set_label(conn, image_id, tag_pending, tag_rejected)
            print("  Screenshot moved to Rejected: " + name)
    conn.commit()
    conn.close()

    with open(common.log_path("pending_review_log.txt"), "a", encoding="utf-8") as log:
        log.write("\n=== " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " ===\n")
        log.write("keep=" + str(len(groups["keep"])) + " reject=" + str(len(groups["reject"]))
                  + " screenshot=" + str(len(groups["screenshot"])) + "\n")
        for name in deleted:
            log.write("  deleted: " + name + "\n")
    print("Done. Reopen digiKam to see the updated labels.")


if __name__ == "__main__":
    sys.exit(main())
