"""
config.example.py  ->  copy to config.py and edit.

    Windows:   copy config.example.py config.py
    macOS/Linux: cp config.example.py config.py

config.py is listed in .gitignore, so your paths, names and dates stay local.
NEVER put your Anthropic API key in this file - it is read from the
ANTHROPIC_API_KEY environment variable (see README).

Use forward slashes in Windows paths (C:/Users/...) so Python does not treat
backslashes as escape characters.
"""
from datetime import date
from pathlib import Path

# ── Your photo library (the folder digiKam watches) ──────────────────────────
PICTURES_ROOT = Path("C:/Users/YOUR_NAME/Pictures")

# ── External tools ───────────────────────────────────────────────────────────
# Full path to exiftool.exe, or just "exiftool" if it is on your PATH.
# On Windows the "exiftool_files" folder must sit NEXT TO exiftool.exe.
EXIFTOOL_PATH = Path("C:/Program Files/ExifTool/exiftool.exe")
FFMPEG_PATH = "ffmpeg"            # or a full path; only needed for videos

# ── digiKam ──────────────────────────────────────────────────────────────────
# digiKam stores its main database in your album root unless you moved it.
# (Settings > Configure digiKam > Database shows the location.)
DIGIKAM_DB = PICTURES_ROOT / "digikam4.db"

# Internal tag IDs digiKam uses for Pick Labels. These are the same on most
# installs but VERIFY on yours:  python tools/inspect_digikam_db.py
TAG_NONE = 19
TAG_REJECTED = 20
TAG_PENDING = 21
TAG_ACCEPTED = 22

# ── Claude API ───────────────────────────────────────────────────────────────
MODEL = "claude-haiku-4-5-20251001"   # cheap + good enough for tagging
PREVIEW_SIZE = 512                    # px, longest side sent to the API
PREVIEW_QUALITY = 85                  # JPEG quality of the previews
PHOTO_BATCH_SIZE = 10                 # photos per API call (autotag.py)
VIDEO_BATCH_SIZE = 6                  # videos per API call
REVIEW_BATCH_SIZE = 5                 # photos per call (blur/pending review)

# ── Folders ──────────────────────────────────────────────────────────────────
# autotag_videos.py skips any folder whose name starts with one of these.
SKIP_PREFIXES = ("!", "1-", "2-")
INBOX_FOLDER = PICTURES_ROOT / "_inbox"          # photo_ingest.py only
LOG_DIR = Path(__file__).resolve().parent / "logs"   # gitignored

# ── Optional: tag one person by age (tag_child_by_age.py / sort_child_by_age.py)
# Leave CHILD_BIRTHDATE as None if you do not use these scripts.
CHILD_NAME = "Firstname"                       # used in messages only
CHILD_TAGS = ["Firstname", "People/Nickname"]  # written to EVERY photo in CHILD_ROOT
CHILD_BIRTHDATE = None                         # e.g. date(2015, 3, 14)
CHILD_ROOT = PICTURES_ROOT / "Family/Firstname"
