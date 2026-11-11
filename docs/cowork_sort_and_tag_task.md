# Cowork task: sort and tag a photo inbox

This is a prompt for [Claude Cowork](https://claude.com) (or any Claude agent
that can run shell commands on your machine). It does everything the Python
scripts do in one hands-off pass: weed out bad photos, group files into event
folders, and tag everything. It is **not scheduled** and does nothing until
you ask for it.

> **Before you use it:** replace the four `<...>` placeholders in the
> "KEY PATHS" section at the bottom with your own paths. Keep your edited
> copy outside the repo (or in a gitignored file) so your paths stay private.

## How to trigger it

1. Open Cowork and add the prompt below (everything under the line) as context.
2. Type: **"Run the photo sort and tag task"**.

## Prerequisites

- ExifTool (with its `exiftool_files` folder on Windows)
- ImageMagick (the `magick` command must be on PATH) - used to make previews
- Cowork permission to read/write your photo folders

> **WARNING:** photos judged blurry, dark, washed out or screenshots are
> **permanently deleted** (no recycle bin). Videos are never deleted. If that
> makes you nervous, change "Permanently delete" in Step 2 to "Move to
> `<PICTURES_ROOT>\3-Review Deleted`" before running.

Cowork: everything above this line is for humans. Ignore it. The task starts below.

---

# TASK: PHOTO AND VIDEO SORT AND TAG

When the user says "run the photo sort and tag task", execute all steps below
automatically without asking the user any questions.

## STEP 1: SCAN THE INBOX

Scan all files in `<INBOX>` and separate them into two lists:

- PHOTO extensions: .jpg, .jpeg, .png, .heic, .tiff, .tif
- VIDEO extensions: .mp4, .mov, .avi, .m4v, .3gp, .mkv, .wmv

If both lists are empty, report "No files found in inbox" and stop.

## STEP 2: PHOTO QUALITY CHECK

For each photo, create a 512px preview with ImageMagick:

    magick "[source]" -resize 512x512 -quality 85 "[preview].jpg"

Examine each preview and assign one verdict:

- **DELETE**: severely blurry or out of focus; very dark or underexposed;
  heavily washed out or overexposed; any screenshot or screen capture (phone
  UI, app, text message, map, website, etc.). Be lenient about quality - only
  delete truly unusable photos. Be strict about screenshots.
- **KEEP**: acceptable quality; will be organized and tagged.

Permanently delete all DELETE photos. Clean up all temp previews.

## STEP 3: VIDEO REVIEW (NO DELETION)

VIDEOS ARE NEVER DELETED. This step is assessment only.

For each video try to extract one frame:

    magick "[video][0]" -resize 512x512 -quality 85 "[preview].jpg"

If extraction fails, continue using EXIF metadata and the filename only. Note
in the final report any video that looks like a screen recording or is under
3 seconds, but do NOT delete it. Clean up all temp frames.

## STEP 4: ANALYZE, GROUP, AND MOVE ALL FILES

For all remaining photos AND all videos together:

1. Read metadata with ExifTool: `<EXIFTOOL> -json "[file]"`. Extract
   DateTimeOriginal or CreateDate, GPSLatitude, GPSLongitude, Make, Model, and
   Duration (videos).
2. Group photos and videos together by date. Treat files as one event if they
   share a date or fall within 1 hour of each other.
3. Within each group decide whether the files share the same context (same
   location, event or subject). A video of the same scene as nearby photos
   belongs in the same folder.
4. For groups of 2+ files from the same day and context:
   - Determine a location or event name from GPS or image content (for example
     "Park", "Beach", "Birthday Party").
   - Create `<PICTURES_ROOT>\<Location> - YYYY-MM-DD` and move ALL related
     photos and videos into it.
5. Single files, or files that do not belong to a clear group, go to
   `<TO_BE_FILED>` (create it if missing).

## STEP 5: TAG ALL FILES

Tag every file in every folder, including the to-be-filed folder.

**Photos**

1. Make 512px previews of the folder's photos (ImageMagick, as above).
2. Examine each preview and generate 3-8 keyword tags: location, subjects,
   activity, time of day, scenery. Do NOT include the year or folder name.
3. In a named folder (not the to-be-filed folder) also add base tags from the
   folder name: the location words and the 4-digit year.
4. Write tags with ExifTool to `XMP:Subject`:
   `<EXIFTOOL> -XMP:Subject+="[tag]" -overwrite_original "[file]"`
5. Write the tag "Claude Reviewed" the same way.
6. Delete the previews.

**Videos**

1. Extract one frame (as in Step 3) and generate 3-8 tags for the content. If
   extraction fails, use the filename and EXIF date only.
2. Add the same folder-name base tags as for photos.
3. Write tags to `XMP:Subject` with ExifTool. If a format cannot hold embedded
   XMP, skip it and say so in the report.
4. Write "Claude Reviewed" to every video. Delete temp frames.

## STEP 6: REPORT

Report: photos processed; videos processed; photos deleted (filenames and
reason); videos that look like screen recordings or are very short (not
deleted); new folders with photo/video counts; files moved to the
to-be-filed folder; tags applied per folder; files that could not be tagged.

## KEY PATHS (edit these)

| Placeholder        | Meaning                                  |
| ------------------ | ---------------------------------------- |
| `<INBOX>`          | folder where new, unsorted files land    |
| `<PICTURES_ROOT>`  | your library root (the folder digiKam watches) |
| `<TO_BE_FILED>`    | folder for files that fit no event       |
| `<EXIFTOOL>`       | full path to exiftool (or `exiftool` if on PATH) |

## IMPORTANT RULES

- Never ask the user any questions - just execute.
- Videos are NEVER deleted under any circumstances.
- Always use `-XMP:Subject` (not `-Keywords`) when writing tags: digiKam reads XMP.
- Always use `-overwrite_original` with ExifTool.
- Deleted photos are permanent. Be lenient: only delete truly unusable photos.
- Group videos with photos when they share the same date and context.
- Use GPS for location names when available; otherwise judge from the image;
  if still unknown, use "Unknown".
