"""
tag_folders.py - Tag several folders in one go (photos and/or videos).

    python tag_folders.py "Zoo - 2023-07-28" "Pets" "Concerts"
    python tag_folders.py --list folders.txt
    python tag_folders.py --list folders.txt --photos-only
    python tag_folders.py "Pets" --videos-only

Folder names are resolved under PICTURES_ROOT unless you give a full path.
--list reads one folder per line (blank lines and lines starting with # are
ignored). Copy folders.example.txt to folders.txt - that file is gitignored,
so your own folder names stay private.

Each folder is processed by autotag.py (photos) and/or autotag_videos.py
(videos) in non-interactive mode. A summary is written to logs/.
"""
import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import common

HERE = Path(__file__).resolve().parent


def read_list(path):
    names = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            names.append(line)
    return names


def count_files(folder, exts):
    return sum(1 for f in folder.iterdir() if f.is_file() and f.suffix.lower() in exts)


def run(script, folder):
    r = subprocess.run([sys.executable, str(HERE / script), str(folder), "--no-prompt"])
    return r.returncode == 0


def main():
    ap = argparse.ArgumentParser(description="Tag multiple folders.")
    ap.add_argument("folders", nargs="*")
    ap.add_argument("--list", help="text file with one folder per line")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--photos-only", action="store_true")
    g.add_argument("--videos-only", action="store_true")
    args = ap.parse_args()

    names = list(args.folders)
    if args.list:
        names += read_list(args.list)
    if not names:
        ap.error("give at least one folder, or --list FILE")

    do_photos = not args.videos_only
    do_videos = not args.photos_only
    ok, bad, skipped = [], [], []

    with open(common.log_path("tag_folders_log.txt"), "a", encoding="utf-8") as log:
        def say(msg=""):
            print(msg)
            log.write(msg + "\n")
            log.flush()

        say("tag_folders run " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        for name in names:
            folder = common.resolve_folder(name)
            if not folder.is_dir():
                say("SKIP (not found): " + name)
                skipped.append(name)
                continue
            n_photos = count_files(folder, common.PHOTO_EXTS) if do_photos else 0
            n_videos = count_files(folder, common.VIDEO_EXTS) if do_videos else 0
            if not (n_photos or n_videos):
                say("SKIP (nothing to tag): " + name)
                skipped.append(name)
                continue
            say("--- " + name + " (" + str(n_photos) + " photos, " + str(n_videos) + " videos) ---")
            good = True
            if n_photos:
                good &= run("autotag.py", folder)
            if n_videos:
                good &= run("autotag_videos.py", folder)
            (ok if good else bad).append(name)
            say("  -> " + ("OK" if good else "FAILED"))

        say("")
        say("COMPLETE  ok=" + str(len(ok)) + " failed=" + str(len(bad)) + " skipped=" + str(len(skipped)))
        for name in bad:
            say("  failed: " + name)
    if bad:
        sys.exit(1)


if __name__ == "__main__":
    main()
