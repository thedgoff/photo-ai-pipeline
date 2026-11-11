# photo-ai-pipeline

Tag, review and organize a large family photo library with
**[digiKam](https://www.digikam.org/)**, **[ExifTool](https://exiftool.org/)** and **Claude** (Anthropic's API, using the
cheap Haiku model). The AI looks at a small preview of each photo, writes
searchable keywords straight into the file's metadata, and digiKam picks them
up. Extra scripts give a second opinion on blurry or "rejected" photos, tag a
family member by age, and sort a messy inbox.

Everything runs locally on your machine; only downscaled previews (512 px by
default) are sent to the Claude API.

> **Status:** a personal project, shared as-is. It works on Windows 11 with
> digiKam 9.0; the code is plain Python and should run on macOS/Linux with
> small path changes. Read the [safety notes](#safety-and-destructive-actions)
> before pointing it at a library you care about, and **keep a backup**.

---

## What's in the box

| Script | What it does |
| --- | --- |
| `autotag.py` | Tags the JPGs in one folder: folder-name tags (place + year) plus 3-8 AI keywords per photo, written to `XMP:Subject`. Drag-and-drop via `autotag.bat` on Windows. |
| `autotag_videos.py` | Same for videos: grabs a frame with ffmpeg, tags it. Never moves or deletes anything. |
| `tag_folders.py` | Tags many folders (photos and/or videos) from the command line or a list file. |
| `tag_child_by_age.py` | Tags every photo under one person's folder with their name tags and their age at the time ("Under 1 Year Old", "3 Years Old", ...). Age comes from EXIF date, then a year in the folder name, then the folder hierarchy. |
| `sort_child_by_age.py` | Moves that person's loose files into `0 Under 1`, `1 Year Old`, `2 Years Old`, ... folders by date. |
| `blur_review.py` | Takes photos digiKam flagged **Rejected**, asks Claude for a second opinion, and moves the fine ones to **Pending**. |
| `pending_review.py` | Reviews **Pending** photos: blurry/dark/washed-out ones become Rejected, screenshots are flagged (or deleted, if you opt in). |
| `photo_ingest.py` | *Experimental, dormant by default.* Watches an inbox, files photos into `City YYYY-MM` folders from EXIF + GPS, then tags them. |
| `tools/inspect_digikam_db.py` | Read-only look at your digiKam database to find the Pick Label tag IDs. |
| `docs/cowork_sort_and_tag_task.md` | A prompt for Claude Cowork that sorts an inbox, drops junk photos, groups event folders and tags everything without any scripts. |

Every photo or video that Claude looked at in the review scripts also gets a
`Claude Reviewed` tag, so you can always filter for what has been assessed.

## How it fits together

```
 new photos --> [1-Files to Sort] --(Cowork task or photo_ingest.py)--> event folders
                                                                           |
        autotag.py / tag_folders.py / autotag_videos.py  <-----------------+
                  |  (Claude Haiku reads previews, ExifTool writes XMP:Subject)
                  v
               digiKam  (imports the files; tags + people + pick labels)
                  |
   blur_review.py / pending_review.py  (read + update digiKam's database)
```

---

## Software you need

| Software | Needed for | Notes |
| --- | --- | --- |
| **Python 3.9+** | everything | Tick "Add python.exe to PATH" in the Windows installer. |
| **`anthropic`**, **`pillow`** (pip) | everything | `pip install -r requirements.txt` |
| **Anthropic API key** | everything that tags/reviews | Create one in the [Anthropic Console](https://console.anthropic.com/) and add a few dollars of credit. |
| **[ExifTool](https://exiftool.org/)** | writing tags | On Windows use the *Windows Executable* zip. The **`exiftool_files` folder must stay next to `exiftool.exe`**. |
| **[digiKam](https://www.digikam.org/)** 8.x/9.x | browsing, pick labels, the review scripts | Tested on 9.0. |
| **[ffmpeg](https://ffmpeg.org/)** | `autotag_videos.py` only | On PATH, or set `FFMPEG_PATH`. |
| `exifread`, `reverse_geocoder` (pip) | `photo_ingest.py` only | `pip install -r requirements-ingest.txt` |
| **[ImageMagick](https://imagemagick.org/)** | Cowork prompt only | `magick` on PATH. |
| **Claude Cowork** (optional) | the no-script sorting task | Only if you want the hands-off inbox workflow. |

## Install

```bash
git clone https://github.com/thedgoff/photo-ai-pipeline.git
cd photo-ai-pipeline
pip install -r requirements.txt
```

**1. Create your private config.** `config.py` holds your paths (and, if you use
the age scripts, a name and birth date). It is in `.gitignore`, so it is never
committed.

```bash
# Windows
copy config.example.py config.py
# macOS / Linux
cp config.example.py config.py
```

Open `config.py` and set at least `PICTURES_ROOT` and `EXIFTOOL_PATH`. Use
forward slashes in Windows paths (`C:/Users/me/Pictures`).

**2. Set your API key as an environment variable.** It is never stored in the
project.

```bat
:: Windows (then open a NEW terminal)
setx ANTHROPIC_API_KEY "your-key-here"
```
```bash
# macOS / Linux (add to ~/.zshrc or ~/.bashrc to make it permanent)
export ANTHROPIC_API_KEY="your-key-here"
```

**3. Check that ExifTool works:** `"C:/path/to/exiftool.exe" -ver` should print a version number.

**4. Run the tests** (offline, no API calls): `python -m unittest discover -s tests -v`

## Using it

### Tag a folder

```bash
python autotag.py "Lake Trip 2017-07"          # relative to PICTURES_ROOT
python autotag.py "D:/Photos/Zoo - 2023-07-28" --no-prompt
python autotag.py "Lake Trip 2017-07" --dry-run  # show tags, write nothing
```

On Windows you can also **drag a folder onto `autotag.bat`**. Without
`--no-prompt` the script finishes by asking for extra comma-separated tags to
apply to every photo in that folder. Then, in digiKam, re-scan the album (or
re-read the metadata of the items) and the tags appear in the tag tree.

Folder names matter: `Lake Trip 2017-07` becomes the tags `2017` and `Lake Trip`
automatically, and the folder name is given to Claude as context.

### Tag many folders / videos

```bash
python tag_folders.py "Zoo - 2023-07-28" "Pets" "Concerts"
python tag_folders.py --list folders.txt          # one folder per line
python tag_folders.py --list folders.txt --videos-only
python autotag_videos.py "Ireland 2019"
```

Copy `folders.example.txt` to `folders.txt` for your list (gitignored). Videos
in sub-folders whose names start with `!`, `1-` or `2-` are skipped
(`SKIP_PREFIXES` in `config.py`), handy for inbox / to-be-filed folders.

### Tag a family member by age

Set `CHILD_NAME`, `CHILD_TAGS`, `CHILD_BIRTHDATE` and `CHILD_ROOT` in
`config.py`, then:

```bash
python tag_child_by_age.py --dry-run
python tag_child_by_age.py            # AI-tag each sub-folder, then add name + age tags
python tag_child_by_age.py --skip-ai  # only the name + age tags
python sort_child_by_age.py --dry-run # preview sorting loose files into age folders
python sort_child_by_age.py
```

A tag like `People/Nickname` creates a *nested* tag in digiKam (`Nickname`
under `People`).

### Review digiKam's blur flags

digiKam's automatic quality sorting marks photos as Pick Label *Rejected* or
*Pending*. These scripts give them a second look.

1. **Close digiKam.**
2. Check the Pick Label IDs: `python tools/inspect_digikam_db.py`. The defaults
   in `config.py` (19-22) match a default install, but yours may differ.
3. Try a cheap dry run: `python blur_review.py --dry-run --limit 20`
4. Run for real: `python blur_review.py` then `python pending_review.py`
5. Reopen digiKam.

Each script backs up the database to `logs/backups/` before changing it.

### Sort an inbox without scripts (Claude Cowork)

[`docs/cowork_sort_and_tag_task.md`](docs/cowork_sort_and_tag_task.md) is a
ready-to-use prompt: it checks an inbox folder, deletes unusable photos and
screenshots, groups files into `<Place> - YYYY-MM-DD` folders, files strays
under *To be Filed*, and tags everything. Fill in the four path placeholders
first and read its deletion warning.

### Auto-ingest (experimental)

`photo_ingest.py` is dormant unless started with `--once` or `--run`. See the
docstring at the top of the file for the Windows Task Scheduler setup.

---

## Safety and destructive actions

- **Back up your library first.** ExifTool rewrites metadata in the files
  themselves (`-overwrite_original`, no `_original` copies).
- **The review scripts edit digiKam's database.** Close digiKam first. A
  timestamped backup is written to `logs/backups/` before every change.
- **Nothing is deleted by default.** `pending_review.py` only deletes
  screenshots if you pass `--delete-screenshots` (permanent; no recycle bin).
  The Cowork prompt *does* delete junk photos; read its warning.
- **When the AI is unsure or a batch fails,** photos are left as they were.
- Use `--dry-run` and `--limit N` to try things on a small sample.

## Cost and privacy

- Roughly **$0.50-$1 per 1,000 photos** with `claude-haiku-4-5` at 512 px
  previews. This is an estimate: check the current
  [pricing](https://www.anthropic.com/pricing) and try a small folder first.
  Smaller `PREVIEW_SIZE` is cheaper; larger batches cost about the same.
- **Your pictures leave your machine** as downscaled JPEG previews sent to the
  Claude API. Read Anthropic's data-usage terms and don't run this on images
  you aren't comfortable sending. File names are not sent by the review
  scripts; `autotag.py` and `autotag_videos.py` do send the file name and the
  folder name as context, so avoid putting private details in them.
- Never commit `config.py`, your API key, digiKam databases, face data or
  photos. `.gitignore` already excludes them.

## Good to know (hard-won lessons)

- **digiKam reads XMP, not IPTC.** ExifTool's `-Keywords` writes IPTC, which
  digiKam 9 ignores for tags. This project always writes
  `-XMP:Subject+=tag`. `+=` skips values that already exist, so re-running a
  folder doesn't create duplicates.
- **Pick Labels are tags** in digiKam's database (`ImageTags`), with IDs that
  you can look up using `tools/inspect_digikam_db.py`.
- **ExifTool on Windows** needs `exiftool_files` next to the `.exe`, or you'll
  see "Could not find exiftool_files\perl5*.dll".
- **A local model did not work out for me.** I tried Ollama (llava, then
  llama3.2-vision): llava hit a vision regression in Ollama 0.13.3+, and the
  larger model was too slow and hot on a laptop. The Haiku API was faster and
  cheap. The code here is API-only.
- If tags don't show up in digiKam, confirm they're in the file
  (`exiftool -XMP:Subject photo.jpg`), then re-scan the album or re-read
  metadata, and check that digiKam is set to read XMP metadata.
- `HEIC`/`PNG` files are accepted by the age scripts, but `autotag.py` only
  tags `.jpg`/`.jpeg`.

## Project layout

```
autotag.py  autotag_videos.py  tag_folders.py
tag_child_by_age.py  sort_child_by_age.py
blur_review.py  pending_review.py  photo_ingest.py
common.py  digikam_db.py        # shared helpers
config.example.py               # copy to config.py (gitignored)
folders.example.txt             # copy to folders.txt (gitignored)
tools/inspect_digikam_db.py
docs/cowork_sort_and_tag_task.md
tests/test_basic.py
```

## Contributing

Issues and pull requests are welcome. Please don't include personal photos,
databases, file names, or API keys in issues or PRs.

## License

[MIT](LICENSE). ExifTool, digiKam, ffmpeg and ImageMagick have their own
licenses and are not included in this repository.
