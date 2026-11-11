"""
autotag_videos.py - Tag video files using Claude (Haiku) + ffmpeg + ExifTool.

    python autotag_videos.py                       # whole PICTURES_ROOT
    python autotag_videos.py "Ireland 2019"        # one folder (and subfolders)
    python autotag_videos.py "Ireland 2019" --dry-run

Walks the folder recursively, skipping any sub-folder whose name starts with a
prefix in SKIP_PREFIXES (default "!", "1-", "2-" - e.g. an inbox and a
to-be-filed folder). For each video, one frame is grabbed with ffmpeg, sent to
Claude, and the returned keywords (plus folder-name tags) are appended to
XMP:Subject. Videos are never moved, edited or deleted - only tagged.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import common

PROMPT = (
    "I'm going to show you thumbnail frames from {n} videos from a folder "
    "called '{folder}'. For each video, return a JSON object with the ORIGINAL "
    "VIDEO filename as the key and an array of keyword tags as the value. Tags "
    "should be useful for library search: subjects, activities, locations, "
    "events, animals, scenery, people (generic like 'child', 'family', not "
    "names). Keep tags concise (1-3 words each). Include 3-8 tags per video. "
    "Do NOT include the folder name or year as tags. Return ONLY a valid JSON "
    "object, no explanation, no markdown, no code fences. Use the exact "
    "filenames I provide. Example:\n"
    '{{"video1.mp4": ["Beach", "Children", "Swimming"], '
    '"video2.mp4": ["Fireworks", "Night", "Outdoor"]}}'
)


def should_skip(name):
    return name.startswith(tuple(common.cfg("SKIP_PREFIXES", ("!", "1-", "2-"))))


def collect_videos(root: Path):
    videos = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        dirnames[:] = [d for d in dirnames if not should_skip(d)]
        for fname in filenames:
            if Path(fname).suffix.lower() in common.VIDEO_EXTS:
                videos.append(Path(dirpath) / fname)
    return sorted(videos)


def extract_thumbnail(video: Path, out: Path, size: int) -> bool:
    ffmpeg = str(common.cfg("FFMPEG_PATH", "ffmpeg"))
    for seek in ("00:00:02", "00:00:00"):  # fall back for very short clips
        cmd = [ffmpeg, "-y", "-ss", seek, "-i", str(video), "-vframes", "1",
               "-vf", "scale=" + str(size) + ":" + str(size)
               + ":force_original_aspect_ratio=decrease",
               "-q:v", "3", str(out)]
        subprocess.run(cmd, capture_output=True, text=True)
        if out.exists():
            return True
    return False


def tag_batch(client, thumbs, folder_name):
    content = [{"type": "text",
                "text": PROMPT.format(n=len(thumbs), folder=folder_name)}]
    for name, thumb in thumbs:
        content.append({"type": "text", "text": "Video filename: " + name})
        content.append(common.image_block(common.file_b64(thumb)))
    return common.ask_json(client, content, max_tokens=1024)


def main():
    ap = argparse.ArgumentParser(description="Tag videos with Claude.")
    ap.add_argument("root", nargs="?", default=None,
                    help="folder to crawl (default: PICTURES_ROOT)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-prompt", action="store_true",
                    help="accepted for compatibility with autotag.py; ignored")
    args = ap.parse_args()

    root = common.resolve_folder(args.root) if args.root else common.pictures_root()
    if not root.is_dir():
        sys.exit("Folder not found: " + str(root))
    if not args.dry_run:
        common.check_exiftool()
    ffmpeg = str(common.cfg("FFMPEG_PATH", "ffmpeg"))
    try:
        subprocess.run([ffmpeg, "-version"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        sys.exit("ffmpeg not found. Install it and put it on PATH, or set FFMPEG_PATH.")
    client = common.get_client()

    videos = collect_videos(root)
    print("")
    print("=" * 50)
    print("  AutoTag Videos: " + str(root) + ("   [DRY RUN]" if args.dry_run else ""))
    print("  Skipping folders starting with: " + str(common.cfg("SKIP_PREFIXES")))
    print("=" * 50)
    print("  Found " + str(len(videos)) + " video(s).")
    if not videos:
        return

    by_folder = defaultdict(list)
    for v in videos:
        by_folder[v.parent].append(v)

    size = common.cfg("PREVIEW_SIZE", 512)
    batch_size = common.cfg("VIDEO_BATCH_SIZE", 6)
    tmp = Path(tempfile.mkdtemp(prefix="autotag_videos_"))
    tagged = failed = 0

    with open(common.log_path("autotag_videos_log.txt"), "a", encoding="utf-8") as log:
        def say(msg=""):
            print(msg)
            log.write(msg + "\n")
            log.flush()

        say("=== autotag_videos run " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            + " | " + str(len(videos)) + " videos ===")
        try:
            for folder, vids in by_folder.items():
                base = common.derive_base_tags(folder.name)
                say("")
                say("Folder: " + folder.name + " (" + str(len(vids)) + " videos), base tags " + str(base))

                thumbs = []
                for idx, v in enumerate(vids):
                    out = tmp / (str(idx) + "_" + v.stem + ".jpg")
                    if extract_thumbnail(v, out, size):
                        thumbs.append((v.name, out))
                    else:
                        say("  WARNING: no thumbnail for " + v.name + " (base tags only)")

                ai = {}
                for i in range(0, len(thumbs), batch_size):
                    try:
                        ai.update(tag_batch(client, thumbs[i:i + batch_size], folder.name))
                    except Exception as exc:
                        say("  WARNING: API batch failed: " + str(exc))

                for v in vids:
                    tags = base + list(ai.get(v.name, []))
                    if common.write_xmp_subject(v, tags, dry_run=args.dry_run):
                        tagged += 1
                        say("  TAGGED: " + v.name + " -> " + str(common.clean_tags(tags)))
                    else:
                        failed += 1
                        say("  FAILED: " + v.name)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        say("")
        say("DONE. Tagged: " + str(tagged) + "  Failed: " + str(failed))
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
