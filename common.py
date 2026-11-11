"""
common.py - helpers shared by every script in this project.

Loads your personal settings from config.py (copy config.example.py to
config.py first) and provides the pieces that were duplicated across the
original scripts: image previews, Claude calls, JSON cleanup, ExifTool
tag writing, folder-name tags and age calculations.
"""
import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

try:
    import config
except ModuleNotFoundError as exc:  # only swallow "config itself is missing"
    if exc.name != "config":
        raise
    sys.exit(
        "config.py not found.\n"
        "Copy config.example.py to config.py, then edit the paths in it.\n"
        "(config.py is gitignored, so your personal settings are never committed.)"
    )

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".wmv", ".mkv", ".3gp", ".webm"}


# ── config access ────────────────────────────────────────────────────────────
def cfg(name, default=None):
    """Read a setting from config.py, falling back to a default."""
    return getattr(config, name, default)


def pictures_root() -> Path:
    root = cfg("PICTURES_ROOT")
    if root is None:
        sys.exit("PICTURES_ROOT is not set in config.py")
    return Path(root)


def resolve_folder(arg) -> Path:
    """Accept an absolute path, or a folder name relative to PICTURES_ROOT."""
    p = Path(arg)
    if p.exists():
        return p
    candidate = pictures_root() / arg
    return candidate if candidate.exists() else p


def log_path(filename: str) -> Path:
    log_dir = Path(cfg("LOG_DIR", Path(__file__).resolve().parent / "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / filename


# ── ExifTool ─────────────────────────────────────────────────────────────────
def exiftool_cmd() -> str:
    return str(cfg("EXIFTOOL_PATH", "exiftool"))


def check_exiftool():
    """Exit with a helpful message if ExifTool cannot run."""
    cmd = exiftool_cmd()
    if not (Path(cmd).exists() or shutil.which(cmd)):
        sys.exit("ExifTool not found: " + cmd + "\nSet EXIFTOOL_PATH in config.py.")
    try:
        r = subprocess.run([cmd, "-ver"], capture_output=True, text=True)
    except OSError as exc:
        sys.exit("ExifTool could not start: " + str(exc))
    if r.returncode != 0:
        sys.exit(
            "ExifTool failed to run: " + (r.stderr or r.stdout).strip() + "\n"
            "On Windows the 'exiftool_files' folder must be next to exiftool.exe."
        )


def clean_tags(tags):
    """Keep non-empty strings, strip whitespace, de-duplicate case-insensitively."""
    seen, out = set(), []
    for t in tags or []:
        if not isinstance(t, str):
            continue
        t = t.strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


def write_xmp_subject(path, tags, dry_run=False) -> bool:
    """
    Append tags to XMP:Subject. digiKam reads XMP (not IPTC Keywords), and
    ExifTool's += skips values that are already present, so re-runs are safe.
    """
    tags = clean_tags(tags)
    if not tags or dry_run:
        return True
    args = [exiftool_cmd()]
    args += ["-XMP:Subject+=" + t for t in tags]
    args += ["-overwrite_original", str(path)]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        print("  WARNING ExifTool error for " + Path(path).name + ": " + r.stderr.strip())
        return False
    return True


def _parse_exif_date(value):
    if not value or len(value) < 10:
        return None
    try:
        return datetime.strptime(value[:10], "%Y:%m:%d").date()
    except ValueError:
        return None  # includes the placeholder "0000:00:00"


def _norm(p) -> str:
    return os.path.normcase(os.path.abspath(str(p)))


def exif_dates(files, chunk=50):
    """Return {path: date or None}, reading dates with a few ExifTool calls."""
    files = [Path(f) for f in files]
    result = {f: None for f in files}
    lookup = {_norm(f): f for f in files}
    for i in range(0, len(files), chunk):
        part = files[i:i + chunk]
        proc = subprocess.run(
            [exiftool_cmd(), "-json", "-DateTimeOriginal", "-CreateDate",
             "-MediaCreateDate"] + [str(f) for f in part],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if not proc.stdout.strip():
            continue
        try:
            records = json.loads(proc.stdout)
        except json.JSONDecodeError:
            continue
        for rec in records:
            f = lookup.get(_norm(rec.get("SourceFile", "")))
            if f is None:
                continue
            for field in ("DateTimeOriginal", "CreateDate", "MediaCreateDate"):
                d = _parse_exif_date(rec.get(field))
                if d:
                    result[f] = d
                    break
    return result


# ── Folder-name tags ─────────────────────────────────────────────────────────
def derive_base_tags(folder_name: str):
    """
    'Lake Trip 2017-07'  -> ['2017', 'Lake Trip']
    'Zoo - 2023-07-28'  -> ['2023', 'Zoo']
    4-digit numbers become year tags; other numbers (month/day) are dropped.
    """
    parts = re.sub(r"[-_.]", " ", folder_name).split()
    tags, words = [], []
    for part in parts:
        if part.isdigit():
            if len(part) == 4:
                tags.append(part)
        else:
            words.append(part)
    if words:
        tags.append(" ".join(words))
    return tags


# ── Age helpers (used by the "tag one person by age" scripts) ────────────────
def age_years(birthdate: date, on: date) -> int:
    years = on.year - birthdate.year
    if (on.month, on.day) < (birthdate.month, birthdate.day):
        years -= 1
    return max(0, years)


def age_tag(years: int) -> str:
    if years == 0:
        return "Under 1 Year Old"
    if years == 1:
        return "1 Year Old"
    return str(years) + " Years Old"


def age_folder_name(years: int) -> str:
    if years == 0:
        return "0 Under 1"
    if years == 1:
        return "1 Year Old"
    return str(years) + " Years Old"


# ── Claude API ───────────────────────────────────────────────────────────────
def get_client():
    """Create an Anthropic client; the key comes from ANTHROPIC_API_KEY only."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit(
            "ANTHROPIC_API_KEY is not set.\n"
            "Windows:  setx ANTHROPIC_API_KEY \"your-key-here\"  (then open a NEW terminal)\n"
            "macOS/Linux:  export ANTHROPIC_API_KEY=\"your-key-here\""
        )
    try:
        import anthropic
    except ImportError:
        sys.exit("The anthropic package is missing. Run: pip install -r requirements.txt")
    return anthropic.Anthropic()


def image_b64(path, size=None, quality=None) -> str:
    """Downscale an image in memory and return it as base64 JPEG."""
    from PIL import Image, ImageOps
    size = size or cfg("PREVIEW_SIZE", 512)
    quality = quality or cfg("PREVIEW_QUALITY", 85)
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        img.thumbnail((size, size), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality)
    return base64.standard_b64encode(buf.getvalue()).decode("utf-8")


def file_b64(path) -> str:
    with open(path, "rb") as fh:
        return base64.standard_b64encode(fh.read()).decode("utf-8")


def image_block(b64: str) -> dict:
    return {"type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}}


def parse_json(text: str):
    """Parse a model reply that should be JSON, tolerating ``` fences / chatter."""
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        raw = raw.rsplit("```", 1)[0]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end > start:
            return json.loads(raw[start:end + 1])
        raise


def ask_json(client, content, max_tokens=1024):
    """Send one user message to Claude and return the parsed JSON reply."""
    resp = client.messages.create(
        model=cfg("MODEL", "claude-haiku-4-5-20251001"),
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": content}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    return parse_json(text)


def assess_batch(client, items, instructions, valid, default):
    """
    Quality-review helper for blur_review.py / pending_review.py.
    items = [(image_id, preview_b64)]. Returns {str(id): verdict}; any missing
    or unrecognised verdict becomes `default` (always the non-destructive one).
    """
    content = [{"type": "text", "text": instructions}]
    for image_id, b64 in items:
        content.append({"type": "text", "text": "Image ID: " + str(image_id)})
        content.append(image_block(b64))
    data = ask_json(client, content, max_tokens=512)
    out = {}
    for image_id, _ in items:
        verdict = str(data.get(str(image_id), default)).strip().lower()
        out[str(image_id)] = verdict if verdict in valid else default
    return out
