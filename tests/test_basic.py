"""
Offline tests: no API calls, no real ExifTool, no personal data.
Run from the repo root:   python -m unittest discover -s tests -v
"""
import os
import sqlite3
import stat
import sys
import tempfile
import types
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="photo_ai_tests_"))
FAKE_EXIFTOOL = TMP / "fake_exiftool.sh"
EXIF_LOG = TMP / "exiftool_calls.txt"
FAKE_EXIFTOOL.write_text(
    "#!/bin/sh\n"
    'if [ "$1" = "-ver" ]; then echo 12.99; exit 0; fi\n'
    'echo "$@" >> "' + str(EXIF_LOG) + '"\n'
)
FAKE_EXIFTOOL.chmod(FAKE_EXIFTOOL.stat().st_mode | stat.S_IEXEC)

cfg = types.ModuleType("config")
cfg.PICTURES_ROOT = TMP / "lib"
cfg.EXIFTOOL_PATH = FAKE_EXIFTOOL
cfg.DIGIKAM_DB = TMP / "digikam4.db"
cfg.LOG_DIR = TMP / "logs"
cfg.TAG_REJECTED, cfg.TAG_PENDING = 20, 21
cfg.CHILD_BIRTHDATE = date(2015, 3, 14)
sys.modules["config"] = cfg

import common  # noqa: E402
import digikam_db as db  # noqa: E402
import tag_child_by_age as tca  # noqa: E402
import sort_child_by_age as sca  # noqa: E402


def make_db(path):
    conn = sqlite3.connect(str(path))
    conn.executescript("""
        CREATE TABLE Albums (id INTEGER PRIMARY KEY, relativePath TEXT);
        CREATE TABLE Images (id INTEGER PRIMARY KEY, album INTEGER, name TEXT, status INTEGER);
        CREATE TABLE ImageTags (imageid INTEGER, tagid INTEGER, UNIQUE(imageid, tagid));
        CREATE TABLE ImageInformation (imageid INTEGER);
    """)
    conn.commit()
    return conn


class PureFunctions(unittest.TestCase):
    def test_base_tags(self):
        self.assertEqual(common.derive_base_tags("Lake Trip 2017-07"), ["2017", "Lake Trip"])
        self.assertEqual(common.derive_base_tags("Zoo - 2023-07-28"), ["2023", "Zoo"])
        self.assertEqual(common.derive_base_tags("Pets"), ["Pets"])

    def test_age(self):
        b = date(2015, 3, 14)
        self.assertEqual(common.age_years(b, date(2015, 3, 14)), 0)
        self.assertEqual(common.age_years(b, date(2016, 3, 13)), 0)
        self.assertEqual(common.age_years(b, date(2016, 3, 14)), 1)
        self.assertEqual(common.age_years(b, date(2024, 6, 1)), 9)
        self.assertEqual(common.age_tag(0), "Under 1 Year Old")
        self.assertEqual(common.age_tag(1), "1 Year Old")
        self.assertEqual(common.age_tag(7), "7 Years Old")
        self.assertEqual(common.age_folder_name(0), "0 Under 1")

    def test_parse_json(self):
        self.assertEqual(common.parse_json('{"a": 1}'), {"a": 1})
        self.assertEqual(common.parse_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(common.parse_json('Sure! {"a": 1} hope that helps'), {"a": 1})

    def test_clean_tags(self):
        self.assertEqual(common.clean_tags([" Beach", "beach", "", None, 5, "Sun"]), ["Beach", "Sun"])

    def test_sort_filename_dates(self):
        self.assertEqual(sca.date_from_filename(Path("2016-05-04 party.jpg")), date(2016, 5, 4))
        self.assertEqual(sca.date_from_filename(Path("20160504_101010.jpg")), date(2016, 5, 4))
        self.assertIsNone(sca.date_from_filename(Path("IMG_0001.jpg")))


class AgeTagging(unittest.TestCase):
    b = date(2015, 3, 14)

    def test_priority_exif_then_folder_then_hierarchy(self):
        root = Path("/x/Child")
        p = root / "Easter 2017" / "a.jpg"
        self.assertEqual(tca.determine_age_tag(p, date(2019, 1, 1), self.b, root), "3 Years Old")
        self.assertEqual(tca.determine_age_tag(p, None, self.b, root), "2 Years Old")  # Jun 2017
        q = root / "3 Years Old" / "Misc" / "b.jpg"
        self.assertEqual(tca.determine_age_tag(q, None, self.b, root), "3 Years Old")
        r = root / "0 Under 1" / "c.jpg"
        self.assertEqual(tca.determine_age_tag(r, None, self.b, root), "Under 1 Year Old")
        self.assertEqual(tca.determine_age_tag(root / "Misc" / "d.jpg", None, self.b, root), "Age Unknown")

    def test_exif_before_birth_is_ignored(self):
        root = Path("/x/Child")
        p = root / "1 Year Old" / "a.jpg"
        self.assertEqual(tca.determine_age_tag(p, date(2010, 1, 1), self.b, root), "1 Year Old")


class DatabaseHelpers(unittest.TestCase):
    def test_label_swap_and_remove(self):
        path = TMP / "helpers.db"
        conn = make_db(path)
        conn.execute("INSERT INTO Albums VALUES (1, '/Trip')")
        conn.execute("INSERT INTO Images VALUES (1, 1, 'a.jpg', 1)")
        conn.execute("INSERT INTO Images VALUES (2, 1, 'gone.jpg', 3)")  # status 3 = removed
        conn.execute("INSERT INTO ImageTags VALUES (1, 20)")
        conn.execute("INSERT INTO ImageTags VALUES (2, 20)")
        conn.execute("INSERT INTO ImageInformation VALUES (1)")
        conn.commit()
        self.assertEqual(db.photos_with_label(conn, 20), [(1, "a.jpg", "/Trip")])
        db.set_label(conn, 1, 20, 21)
        self.assertEqual(db.photos_with_label(conn, 20), [])
        self.assertEqual(db.photos_with_label(conn, 21), [(1, "a.jpg", "/Trip")])
        db.remove_image(conn, 1)  # tables that don't exist must not crash
        conn.commit()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM Images WHERE id=1").fetchone()[0], 0)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM ImageInformation").fetchone()[0], 0)
        backup = db.backup_db(path, TMP / "bk")
        self.assertTrue(backup.exists())


class FakeClient:
    """Stands in for anthropic.Anthropic; answers keep/reject by image id."""
    def __init__(self, answers):
        self.answers = answers
        self.messages = self

    def create(self, **kwargs):
        import json
        text = json.dumps(self.answers)
        return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text=text)])


class ReviewScriptsEndToEnd(unittest.TestCase):
    def setUp(self):
        from PIL import Image
        (cfg.PICTURES_ROOT / "Trip").mkdir(parents=True, exist_ok=True)
        for n in ("good.jpg", "bad.jpg", "shot.jpg"):
            Image.new("RGB", (800, 600), (120, 90, 60)).save(cfg.PICTURES_ROOT / "Trip" / n)
        if cfg.DIGIKAM_DB.exists():
            cfg.DIGIKAM_DB.unlink()
        conn = make_db(cfg.DIGIKAM_DB)
        conn.execute("INSERT INTO Albums VALUES (1, '/Trip')")
        for i, n in ((1, "good.jpg"), (2, "bad.jpg"), (3, "shot.jpg")):
            conn.execute("INSERT INTO Images VALUES (?, 1, ?, 1)", (i, n))
        conn.commit()
        conn.close()
        if EXIF_LOG.exists():
            EXIF_LOG.unlink()

    def labels(self):
        conn = sqlite3.connect(str(cfg.DIGIKAM_DB))
        out = sorted(conn.execute("SELECT imageid, tagid FROM ImageTags"))
        conn.close()
        return out

    def seed(self, tag):
        conn = sqlite3.connect(str(cfg.DIGIKAM_DB))
        conn.executemany("INSERT INTO ImageTags VALUES (?, ?)", [(1, tag), (2, tag), (3, tag)])
        conn.commit()
        conn.close()

    def run_script(self, module_name, answers, argv):
        mod = __import__(module_name)
        with mock.patch.object(common, "get_client", return_value=FakeClient(answers)), \
             mock.patch.object(sys, "argv", [module_name + ".py"] + argv):
            mod.main()

    def test_blur_review_moves_keepers_to_pending(self):
        self.seed(20)
        self.run_script("blur_review", {"1": "keep", "2": "reject", "3": "garbage"}, [])
        self.assertEqual(self.labels(), [(1, 21), (2, 20), (3, 20)])
        self.assertIn("Claude Reviewed", EXIF_LOG.read_text())

    def test_blur_review_dry_run_changes_nothing(self):
        self.seed(20)
        self.run_script("blur_review", {"1": "keep"}, ["--dry-run"])
        self.assertEqual(self.labels(), [(1, 20), (2, 20), (3, 20)])
        self.assertFalse(EXIF_LOG.exists())

    def test_pending_review_safe_default_keeps_screenshot_file(self):
        self.seed(21)
        self.run_script("pending_review", {"1": "keep", "2": "reject", "3": "screenshot"}, [])
        self.assertEqual(self.labels(), [(1, 21), (2, 20), (3, 20)])
        self.assertTrue((cfg.PICTURES_ROOT / "Trip" / "shot.jpg").exists())
        self.assertIn("Screenshot", EXIF_LOG.read_text())

    def test_pending_review_delete_screenshots_flag(self):
        self.seed(21)
        self.run_script("pending_review", {"1": "keep", "2": "keep", "3": "screenshot"},
                        ["--delete-screenshots"])
        self.assertFalse((cfg.PICTURES_ROOT / "Trip" / "shot.jpg").exists())
        self.assertTrue((cfg.PICTURES_ROOT / "Trip" / "good.jpg").exists())
        self.assertEqual(self.labels(), [(1, 21), (2, 21)])

    def test_pending_review_missing_verdict_leaves_photo_alone(self):
        self.seed(21)
        self.run_script("pending_review", {"1": "reject"}, [])  # 2 and 3 get default "keep"
        self.assertEqual(self.labels(), [(1, 20), (2, 21), (3, 21)])


class AutotagEndToEnd(unittest.TestCase):
    def test_autotag_writes_base_and_ai_tags(self):
        from PIL import Image
        folder = cfg.PICTURES_ROOT / "Lake Trip 2017-07"
        folder.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (640, 480), (10, 120, 200)).save(folder / "a.jpg")
        if EXIF_LOG.exists():
            EXIF_LOG.unlink()
        import autotag
        client = FakeClient({"a.jpg": ["Beach", "Sunset"]})
        with mock.patch.object(common, "get_client", return_value=client), \
             mock.patch.object(sys, "argv", ["autotag.py", "Lake Trip 2017-07", "--no-prompt"]):
            autotag.main()
        call = EXIF_LOG.read_text()
        for tag in ("2017", "Lake Trip", "Beach", "Sunset"):
            self.assertIn("-XMP:Subject+=" + tag, call)
        self.assertNotIn("-Keywords", call)

    def test_autotag_dry_run_writes_nothing(self):
        from PIL import Image
        folder = cfg.PICTURES_ROOT / "Dry Run 2020-01"
        folder.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (640, 480), (10, 120, 200)).save(folder / "a.jpg")
        if EXIF_LOG.exists():
            EXIF_LOG.unlink()
        import autotag
        with mock.patch.object(common, "get_client", return_value=FakeClient({"a.jpg": ["X"]})), \
             mock.patch.object(sys, "argv", ["autotag.py", str(folder), "--dry-run"]):
            autotag.main()
        self.assertFalse(EXIF_LOG.exists())

    def test_sort_child_dry_run(self):
        root = cfg.PICTURES_ROOT / "Family" / "Kid"
        root.mkdir(parents=True, exist_ok=True)
        (root / "2016-05-04 x.jpg").write_bytes(b"x")
        cfg.CHILD_ROOT = root
        with mock.patch.object(sys, "argv", ["sort_child_by_age.py", "--dry-run"]):
            sca.main()
        self.assertTrue((root / "2016-05-04 x.jpg").exists())
        with mock.patch.object(sys, "argv", ["sort_child_by_age.py"]):
            sca.main()
        self.assertTrue((root / "1 Year Old" / "2016-05-04 x.jpg").exists())


if __name__ == "__main__":
    unittest.main()
