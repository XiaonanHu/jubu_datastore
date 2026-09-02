#!/usr/bin/env python3
"""Publish one course story into buju_website/pilot-courses/.

Run from the jubu_datastore repo root as a script (never `python -m`,
never PYTHONPATH=.):

    python scripts/publish_course.py --story story_definitions/stories/courses/<file>.json --dry-run
    python scripts/publish_course.py --story story_definitions/stories/courses/<file>.json

What it does, in this order:
  1. re-runs the course validator and refuses to publish a failing story
  2. copies narration clips  -> pilot-courses/audio/<story_id>/
  3. copies scene images     -> pilot-courses/images/<story_id>/
     and rewrites each segment's `image` to the web path
  4. splices the story JSON into pilot-courses/index.html between the
     __STORY_START__ / __STORY_END__ markers
  5. verifies every file the page references actually exists on disk

Order matters for the same reason it does in publish_pilot_audio.py: assets
land before the data that points at them, so the page can never reference a
clip that isn't there.

Splicing is split/join on unique markers, never regex and never .replace on
user-ish text — the explorer build died twice to quote-escaping before that
rule existed.
"""
from __future__ import annotations
import argparse, json, shutil, subprocess, sys
from pathlib import Path

START = "/*__STORY_START__*/"
END = "/*__STORY_END__*/"


def find_repo(p: Path) -> Path:
    return next((q for q in p.resolve().parents if (q / "story_definitions").is_dir()), p.parent)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--story", required=True)
    ap.add_argument("--website", default="../buju_website",
                    help="path to the buju_website checkout")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-check", action="store_true",
                    help="publish even if the validator fails (don't)")
    a = ap.parse_args()

    sp = Path(a.story).resolve()
    story = json.loads(sp.read_text())
    repo = find_repo(sp)
    base = repo / "story_definitions"
    site = Path(a.website).resolve()
    # The story JSON lives in whichever file carries the markers. It is
    # course.js, not index.html: the site CSP is `script-src 'self'`, so the
    # player's JS cannot be inline or the browser refuses to run it.
    root = site / "pilot-courses"
    page = next((f for f in (root / "course.js", root / "index.html")
                 if f.exists() and START in f.read_text()), None)
    if page is None:
        print(f"! no file under {root} carries {START}. Expected course.js.")
        return 1

    # 1. validator ---------------------------------------------------------
    checker = repo / "scripts" / "check_course_story.py"
    if checker.exists() and not a.skip_check:
        r = subprocess.run([sys.executable, str(checker), str(sp)],
                           capture_output=True, text=True, cwd=repo)
        print(r.stdout.rstrip())
        if r.returncode != 0:
            print("\n! validator FAILED — not publishing. Fix, or --skip-check "
                  "if you know why.")
            return 1

    audio_src = base / "preview" / "course_audio" / story["id"]
    image_src = base / "preview" / "course_images" / story["id"]
    audio_dst = site / "pilot-courses" / "audio" / story["id"]
    image_dst = site / "pilot-courses" / "images" / story["id"]

    manifest = (story.get("audio") or {}).get("segments") or {}
    missing: list[str] = []

    # 2. audio -------------------------------------------------------------
    clips = [m["file"] for m in manifest.values() if m.get("file")]
    print(f"\naudio: {len(clips)} clip(s) from {audio_src}")
    if clips and not a.dry_run:
        audio_dst.mkdir(parents=True, exist_ok=True)
    keep_audio = set(clips)
    for f in clips:
        s = audio_src / f
        if not s.exists():
            missing.append(f"audio/{f}"); print(f"  MISSING {f}"); continue
        if a.dry_run:
            print(f"  would copy {f} ({s.stat().st_size//1024} KB)")
        else:
            shutil.copy2(s, audio_dst / f)
            print(f"  {f} ({s.stat().st_size//1024} KB)")

    # 3. images ------------------------------------------------------------
    imgs = [(s["id"], s.get("image")) for s in story["segments"] if s.get("image")]
    no_img = [s["id"] for s in story["segments"] if not s.get("image")]
    print(f"\nimages: {len(imgs)} of {len(story['segments'])} scene(s)")
    if no_img:
        print(f"  ! no image yet for {no_img} — those segments show a placeholder.")
        print(f"    python scripts/generate_story_images.py --story <path> --only {' '.join(no_img)}")
    if imgs and not a.dry_run:
        image_dst.mkdir(parents=True, exist_ok=True)
    for seg_id, rel in imgs:
        # Resolve from the GENERATOR's output dir first, preferring webp. The
        # recorded `rel` may already be a web path from an earlier publish,
        # which resolves against nothing on disk — trusting it silently
        # re-shipped the 1.5 MB PNGs.
        candidates = [image_src / f"{seg_id}.webp", image_src / f"{seg_id}.png"]
        if not Path(rel).is_absolute():
            candidates.append(base / rel)
        src = next((c for c in candidates if c.exists()), None)
        if src is None:
            missing.append(f"image/{seg_id}"); print(f"  MISSING {seg_id}"); continue
        web = f"/pilot-courses/images/{story['id']}/{src.name}"
        if a.dry_run:
            print(f"  would copy {src.name} -> {web}")
        else:
            shutil.copy2(src, image_dst / src.name)
            print(f"  {src.name} -> {web}")
        for s in story["segments"]:
            if s["id"] == seg_id:
                s["image"] = web

    if missing:
        print(f"\n! {len(missing)} referenced file(s) missing: {missing}")
        print("  Generate them first:")
        print("    python scripts/generate_course_audio.py --story <path>")
        print("    python scripts/generate_story_images.py --story <path>")
        if not a.dry_run:
            return 1

    # 4. splice ------------------------------------------------------------
    html = page.read_text()
    if START not in html or END not in html:
        print(f"\n! markers not found in {page.name}. The page must contain "
              f"`const STORY = {START}{{...}}{END};`")
        return 1
    head, rest = html.split(START, 1)
    _, tail = rest.split(END, 1)
    blob = json.dumps(story, ensure_ascii=False, indent=2)
    out = head + START + blob + END + tail

    if a.dry_run:
        print(f"\nwould splice {len(blob)} bytes of story JSON into {page.name}")
        print("(dry run — nothing written)")
        return 0

    page.write_text(out)
    sp.write_text(json.dumps(story, indent=2, ensure_ascii=False))
    print(f"\nspliced story into {page.relative_to(site)}")

    # 5. verify ------------------------------------------------------------
    bad = []
    for m in manifest.values():
        if m.get("file") and not (audio_dst / m["file"]).exists():
            bad.append(m["file"])
    for s in story["segments"]:
        w = s.get("image")
        if w and not (site / w.lstrip("/")).exists():
            bad.append(w)
    if bad:
        print(f"! post-publish check FAILED, {len(bad)} missing: {bad}")
        return 1
    # Sweep stale assets LAST: a .png left after the switch to .webp is dead
    # weight the browser never asks for. This runs after the splice on purpose
    # — housekeeping must never be able to lose a publish.
    keep_img = {Path(s["image"]).name for s in story["segments"] if s.get("image")}
    for d, keep in ((audio_dst, keep_audio), (image_dst, keep_img)):
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if f.is_file() and f.name not in keep:
                size = f.stat().st_size // 1024
                try:
                    f.unlink()
                    print(f"  swept stale {f.name} ({size} KB)")
                except OSError as e:
                    print(f"  could not sweep {f.name} ({size} KB): {e.strerror}. "
                          f"Delete it by hand.")

    voiced = sum(1 for m in manifest.values() if m.get("words"))
    print(f"verified: {len(clips)} clip(s), {len(imgs)} image(s), "
          f"{voiced} with word timings.")
    print("\nOpen buju_website/pilot-courses/ locally, then commit and push "
          "buju_website to deploy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
