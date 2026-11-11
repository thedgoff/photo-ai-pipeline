"""
photo_ingest.py - EXPERIMENTAL inbox watcher (dormant unless started with --run).

Polls INBOX_FOLDER for new photos, files each one into a folder named
"<City> YYYY-MM" (from EXIF date + GPS, reverse-geocoded offline), then runs
autotag.py on that folder. Photos without GPS go to "Photos YYYY-MM"; without
a date, to "Unsorted <today>".

Extra dependencies (not needed by the rest of the project):
    pip install -r requirements-ingest.txt

Try it by hand first:
    python photo_ingest.py --once      # process the inbox one time and exit
    python photo_ingest.py --run       # keep polling every 30 s (Ctrl+C to stop)

To start it at login on Windows: Task Scheduler > Create Basic Task >
Trigger "When I log on" > Action "Start a program" with
    Program:   python
    Arguments: "C:/path/to/photo-ai-pipeline/photo_ingest.py" --run
Disable the task in Task Scheduler to deactivate it.
"""
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import common

if "--run" not in sys.argv and "--once" not in sys.argv:
    print("photo_ingest.py is dormant. Use --once to process the inbox once,")
    print("or --run to keep watching it. Read the top of this file first.")
    sys.exit(0)

POLL_INTERVAL = 30  # seconds
HERE = Path(__file__).resolve().parent


def exif_datetime(path):
    try:
        import exifread
        with open(path, "rb") as fh:
            tags = exifread.process_file(fh, stop_tag="EXIF DateTimeOriginal", details=False)
        text = str(tags.get("EXIF DateTimeOriginal", "")).strip()
        if text:
            return datetime.strptime(text, "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return None


def gps_place(path):
    """Nearest place name for the photo's GPS position, or None."""
    try:
        import exifread
        import reverse_geocoder as rg

        with open(path, "rb") as fh:
            tags = exifread.process_file(fh, details=False)

        def to_decimal(values, ref):
            d, m, s = (float(v.num) / float(v.den) for v in values[:3])
            dec = d + m / 60 + s / 3600
            return -dec if ref in ("S", "W") else dec

        lat, lon = tags.get("GPS GPSLatitude"), tags.get("GPS GPSLongitude")
        if lat and lon:
            point = (to_decimal(lat.values, str(tags.get("GPS GPSLatitudeRef", "N"))),
                     to_decimal(lon.values, str(tags.get("GPS GPSLongitudeRef", "E"))))
            hits = rg.search(point, verbose=False)
            if hits:
                return hits[0].get("name") or None
    except Exception:
        pass
    return None


def folder_name_for(path):
    when, place = exif_datetime(path), gps_place(path)
    if not when:
        return "Unsorted " + datetime.now().strftime("%Y-%m-%d")
    stamp = when.strftime("%Y-%m")
    return (place + " " + stamp) if place else ("Photos " + stamp)


def unique(dest: Path) -> Path:
    n = 1
    candidate = dest
    while candidate.exists():
        candidate = dest.with_name(dest.stem + "_" + str(n) + dest.suffix)
        n += 1
    return candidate


def process_inbox():
    inbox = Path(common.cfg("INBOX_FOLDER", common.pictures_root() / "_inbox"))
    library = common.pictures_root()
    if not inbox.exists():
        inbox.mkdir(parents=True)
        print("Created inbox folder: " + str(inbox))
        return
    photos = [f for f in inbox.iterdir()
              if f.is_file() and f.suffix.lower() in common.PHOTO_EXTS]
    if not photos:
        return

    groups = {}
    for photo in photos:
        groups.setdefault(folder_name_for(photo), []).append(photo)

    for name, group in groups.items():
        target = library / name
        target.mkdir(exist_ok=True)
        print("Folder: " + name + " (" + str(len(group)) + " photos)")
        for photo in group:
            shutil.move(str(photo), str(unique(target / photo.name)))
        r = subprocess.run([sys.executable, str(HERE / "autotag.py"),
                            str(target), "--no-prompt"])
        print("  tagged" if r.returncode == 0 else "  WARNING autotag exit " + str(r.returncode))


def main():
    print("Photo ingest ACTIVE. Inbox: " + str(common.cfg("INBOX_FOLDER")))
    once = "--once" in sys.argv
    while True:
        try:
            process_inbox()
        except Exception as exc:
            print("ERROR: " + str(exc))
        if once:
            break
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
