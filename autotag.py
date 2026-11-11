"""
autotag.py - Tag the JPG photos in one folder using Claude (Haiku) + ExifTool.

    python autotag.py "Lake Trip 2017-07"            # relative to PICTURES_ROOT
    python autotag.py "D:/Photos/Lake Trip 2017-07"  # or a full path
    python autotag.py "Lake Trip 2017-07" --no-prompt
    python autotag.py "Lake Trip 2017-07" --dry-run  # show tags, write nothing

What happens:
  1. Base tags come from the folder name (a 4-digit year + the place words).
  2. Each photo is downscaled in memory and sent to Claude in batches.
  3. Claude's keywords + the base tags are appended to XMP:Subject (what
     digiKam reads).
  4. Unless --no-prompt is given, you may type extra comma-separated tags
     to apply to every photo in the folder.
"""
import argparse
import sys
from pathlib import Path

import common

PROMPT = (
    "I'm going to show you {n} photos from a folder called '{folder}'. "
    "For each photo, return a JSON object with the filename as the key and an "
    "array of keyword tags as the value. Tags should be specific and useful for "
    "photo library search: location names, subjects, events, time of day, "
    "landmarks, activities, scenery. Keep tags concise (1-3 words each). "
    "Include 3-8 tags per photo. Do NOT include the folder name or year as "
    "tags - those are already handled. Return ONLY a valid JSON object, no "
    "explanation, no markdown, no code fences. Example:\n"
    '{{"photo1.jpg": ["Beach", "Sunset", "Ocean"], '
    '"photo2.jpg": ["Lighthouse", "Coastal", "Daytime"]}}'
)


def tag_batch(client, batch, folder_name):
    content = [{"type": "text",
                "text": PROMPT.format(n=len(batch), folder=folder_name)}]
    for jpg in batch:
        content.append({"type": "text", "text": "Filename: " + jpg.name})
        content.append(common.image_block(common.image_b64(jpg)))
    return common.ask_json(client, content, max_tokens=1024)


def main():
    ap = argparse.ArgumentParser(description="Tag photos in a folder with Claude.")
    ap.add_argument("folder")
    ap.add_argument("--no-prompt", action="store_true",
                    help="skip the extra-tags question (for batch scripts)")
    ap.add_argument("--dry-run", action="store_true",
                    help="call the API and print tags, but do not write them")
    args = ap.parse_args()

    folder = common.resolve_folder(args.folder)
    if not folder.is_dir():
        sys.exit("Folder not found: " + str(folder))

    if not args.dry_run:
        common.check_exiftool()
    client = common.get_client()

    base_tags = common.derive_base_tags(folder.name)
    jpgs = sorted(f for f in folder.iterdir()
                  if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg"))

    print("")
    print("=" * 50)
    print("  AutoTag: " + folder.name + ("   [DRY RUN]" if args.dry_run else ""))
    print("=" * 50)
    print("  Base tags: " + str(base_tags))
    if not jpgs:
        print("  No JPG files found - nothing to do.")
        return
    print("  Photos found: " + str(len(jpgs)))

    size = common.cfg("PHOTO_BATCH_SIZE", 10)
    total = (len(jpgs) + size - 1) // size
    ai_tags, failed_batches = {}, 0
    print("")
    print("Analyzing with Claude (batches of " + str(size) + ")...")
    for i in range(0, len(jpgs), size):
        batch = jpgs[i:i + size]
        print("  Batch " + str(i // size + 1) + " of " + str(total))
        try:
            ai_tags.update(tag_batch(client, batch, folder.name))
        except Exception as exc:  # keep going; base tags still get written
            failed_batches += 1
            print("  WARNING batch failed: " + str(exc))

    print("")
    print("Writing tags to XMP..." if not args.dry_run else "Tags (not written):")
    for jpg in jpgs:
        tags = base_tags + list(ai_tags.get(jpg.name, []))
        common.write_xmp_subject(jpg, tags, dry_run=args.dry_run)
        print("  OK " + jpg.name + ": " + str(common.clean_tags(tags)))

    if not args.no_prompt and not args.dry_run:
        print("")
        print("Enter extra tags for ALL photos in this folder, comma separated")
        print("(e.g. Family, Vacation) or press Enter to skip.")
        try:
            answer = input("  Your extra tags: ").strip()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        extra = [t.strip() for t in answer.split(",") if t.strip()]
        for jpg in jpgs:
            common.write_xmp_subject(jpg, extra)
        if extra:
            print("  Extra tags applied: " + str(extra))

    print("")
    print("DONE: " + str(len(jpgs)) + " photos processed, "
          + str(failed_batches) + " failed batch(es).")
    print("In digiKam, re-scan the album or re-read metadata to see the tags.")
    if failed_batches:
        sys.exit(2)


if __name__ == "__main__":
    main()
