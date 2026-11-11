"""
sort_child_by_age.py - Move loose files in CHILD_ROOT into age folders.

    python sort_child_by_age.py --dry-run   # preview the moves
    python sort_child_by_age.py             # do it

Folders created inside CHILD_ROOT: "0 Under 1", "1 Year Old", "2 Years Old", ...
Only files sitting directly in CHILD_ROOT are moved (sub-folders are untouched).
The date comes from EXIF, else from a YYYY-MM-DD or YYYYMMDD filename prefix;
files with no usable date are left where they are. Name collisions get a
-1, -2 ... suffix, so nothing is overwritten.
"""
import argparse
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

import common


def date_from_filename(path: Path):
    stem = path.stem
    for fmt, n in (("%Y-%m-%d", 10), ("%Y%m%d", 8)):
        try:
            return datetime.strptime(stem[:n], fmt).date()
        except ValueError:
            pass
    return None


def unique_destination(src: Path, folder: Path) -> Path:
    dst = folder / src.name
    n = 1
    while dst.exists():
        dst = folder / (src.stem + "-" + str(n) + src.suffix)
        n += 1
    return dst


def main():
    ap = argparse.ArgumentParser(description="Sort a person's loose files into age folders.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    birthdate = common.cfg("CHILD_BIRTHDATE")
    root = Path(common.cfg("CHILD_ROOT", ""))
    if not isinstance(birthdate, date):
        sys.exit("Set CHILD_BIRTHDATE in config.py first.")
    if not root.is_dir():
        sys.exit("CHILD_ROOT not found: " + str(root))
    common.check_exiftool()

    loose = sorted(f for f in root.iterdir()
                   if f.is_file() and f.suffix.lower() in common.PHOTO_EXTS | common.VIDEO_EXTS)
    print("Loose files in " + str(root) + ": " + str(len(loose)))
    dates = common.exif_dates(loose)

    moved, undated = 0, []
    for f in loose:
        d = dates.get(f) or date_from_filename(f)
        if d is None:
            undated.append(f.name)
            print("  NO DATE (left in place): " + f.name)
            continue
        folder = root / common.age_folder_name(common.age_years(birthdate, d))
        if not args.dry_run:
            folder.mkdir(exist_ok=True)
            dst = unique_destination(f, folder)
            shutil.move(str(f), str(dst))
        print("  " + ("WOULD MOVE" if args.dry_run else "MOVED") + ": " + f.name + " -> " + folder.name)
        moved += 1

    print("")
    print(("Would move " if args.dry_run else "Moved ") + str(moved) + " file(s); "
          + str(len(undated)) + " had no date.")

    with open(common.log_path("sort_child_by_age_log.txt"), "a", encoding="utf-8") as log:
        log.write("=== " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                  + (" (dry run)" if args.dry_run else "") + " moved=" + str(moved) + "\n")
        for name in undated:
            log.write("  no date: " + name + "\n")


if __name__ == "__main__":
    main()
