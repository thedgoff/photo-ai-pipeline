"""
tag_child_by_age.py - Tag every photo under one person's folder with their
name tags and their age at the time of the photo.

Configure CHILD_NAME, CHILD_TAGS, CHILD_BIRTHDATE and CHILD_ROOT in config.py.

    python tag_child_by_age.py             # AI-tag each sub-folder, then add name + age tags
    python tag_child_by_age.py --skip-ai   # only write the name + age tags
    python tag_child_by_age.py --dry-run   # report what would be written

For each photo the age comes from (first match wins):
  1. the EXIF date                      (most accurate)
  2. a 4-digit year in the folder name  (assumed to be June 1st of that year)
  3. a parent folder such as "3 Years Old" or "0 Under 1"
else the tag "Age Unknown" is written.

Tags written: everything in CHILD_TAGS, plus
  "Under 1 Year Old" / "1 Year Old" / "N Years Old".
"""
import argparse
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import common

HERE = Path(__file__).resolve().parent


def year_from_folder_name(name):
    m = re.search(r"\b((?:19|20)\d{2})\b", name)
    return date(int(m.group(1)), 6, 1) if m else None


def age_from_folder_hierarchy(photo: Path, root: Path):
    """Look for 'N Years Old' / '1 Year Old' / '0 Under 1' in the folder path."""
    for folder in [photo.parent] + list(photo.parents):
        if folder == root.parent:
            break
        name = folder.name.lower()
        if "under 1" in name:
            return 0
        m = re.search(r"(\d+)\s+year", name)
        if m:
            return int(m.group(1))
        if folder == root:
            break
    return None


def determine_age_tag(photo, exif_date, birthdate, root):
    if exif_date and exif_date >= birthdate:
        return common.age_tag(common.age_years(birthdate, exif_date))
    fd = year_from_folder_name(photo.parent.name)
    if fd and fd >= birthdate:
        return common.age_tag(common.age_years(birthdate, fd))
    hier = age_from_folder_hierarchy(photo, root)
    if hier is not None:
        return common.age_tag(hier)
    return "Age Unknown"


def photo_folders(root: Path):
    out = []
    for folder in [root] + sorted(p for p in root.rglob("*") if p.is_dir()):
        if "_previews" in folder.name:
            continue
        photos = sorted(f for f in folder.iterdir()
                        if f.is_file() and f.suffix.lower() in common.PHOTO_EXTS)
        if photos:
            out.append((folder, photos))
    return out


def main():
    ap = argparse.ArgumentParser(description="Tag a person's photos with name + age.")
    ap.add_argument("--skip-ai", action="store_true", help="do not call autotag.py")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    birthdate = common.cfg("CHILD_BIRTHDATE")
    root = Path(common.cfg("CHILD_ROOT", ""))
    always = list(common.cfg("CHILD_TAGS", []))
    name = common.cfg("CHILD_NAME", "this person")
    if not isinstance(birthdate, date):
        sys.exit("Set CHILD_BIRTHDATE (e.g. date(2015, 3, 14)) in config.py first.")
    if not root.is_dir():
        sys.exit("CHILD_ROOT not found: " + str(root) + "\nSet it in config.py.")
    if not args.dry_run:
        common.check_exiftool()
    if not args.skip_ai and not args.dry_run:
        common.get_client()  # fail early if the API key is missing

    folders = photo_folders(root)
    total = sum(len(p) for _, p in folders)
    print("")
    print("=" * 50)
    print("  Age tagging for " + name + ("   [DRY RUN]" if args.dry_run else ""))
    print("  Tags on every photo: " + str(always) + " + age")
    print("  " + str(len(folders)) + " folders, " + str(total) + " photos under " + str(root))
    print("=" * 50)

    summary, ai_failed, write_errors = {}, [], []
    for n, (folder, photos) in enumerate(folders, 1):
        rel = folder.relative_to(root) if folder != root else Path(".")
        print("")
        print("[" + str(n) + "/" + str(len(folders)) + "] " + str(rel) + "  (" + str(len(photos)) + " photos)")

        if not args.skip_ai and not args.dry_run:
            r = subprocess.run([sys.executable, str(HERE / "autotag.py"),
                                str(folder), "--no-prompt"], timeout=3600)
            if r.returncode != 0:
                ai_failed.append(str(rel))

        dates = common.exif_dates(photos)
        for photo in photos:
            tag = determine_age_tag(photo, dates.get(photo), birthdate, root)
            ok = common.write_xmp_subject(photo, always + [tag], dry_run=args.dry_run)
            if ok:
                summary[tag] = summary.get(tag, 0) + 1
            else:
                write_errors.append(str(rel / photo.name))
            print("    [" + ("OK" if ok else "ERR") + "] " + photo.name + " -> " + tag)

    print("")
    print("=" * 50)
    print("  COMPLETE")
    for tag in sorted(summary):
        print("    " + tag + ": " + str(summary[tag]))
    print("  AI tagging problems in " + str(len(ai_failed)) + " folder(s); "
          + str(len(write_errors)) + " tag write error(s)")

    with open(common.log_path("tag_child_by_age_log.txt"), "a", encoding="utf-8") as log:
        log.write("\n=== " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " ===\n")
        for tag in sorted(summary):
            log.write("  " + tag + ": " + str(summary[tag]) + "\n")
        for f in ai_failed:
            log.write("  AI failed: " + f + "\n")
        for f in write_errors:
            log.write("  write error: " + f + "\n")
    if ai_failed or write_errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
