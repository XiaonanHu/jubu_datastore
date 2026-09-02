#!/usr/bin/env python3
"""One square cover image per story, for the parent map's topic discs.

Run from the jubu_datastore repo root as a script (never `python -m`,
never PYTHONPATH=.):

    # step 1 only: derive + print the cover direction, spend no image quota
    python scripts/generate_story_covers.py --stories ants --direction-only

    # see the EXACT prompts both calls would send, spend nothing at all
    python scripts/generate_story_covers.py --stories ants --prompt-only

    # generate for named stories (there is deliberately no --all)
    python scripts/generate_story_covers.py --stories ants bees

    # redo one after editing cover_direction on the story file
    python scripts/generate_story_covers.py --stories ants --force

TWO STEPS, SAME PATTERN AS THE SCENE ILLUSTRATOR.

  Step 1 (text model): turn the story + its metadata into ONE drawable
  cover moment — {"scene", "mood"} — written back onto the story file as
  `cover_direction`, so it is reviewable, editable and stable across
  reruns. When the story already carries an `art_direction` (from
  generate_story_images.py), its CAST and ANCHOR paragraphs are reused
  VERBATIM in the cover prompt, so the cover shows the same characters as
  the scene pictures.

  Step 2 (image model): draw it, square, through the shared generate()
  helper in generate_story_images.py.

WHERE COVERS GO. The webp lands in the buju_website repo:
pilot/img/covers/<story_id>.webp, and pilot/data/covers.json lists every
story that has one — that manifest is what makes the map show the cover.
Commit both. LOOK AT EVERY IMAGE before committing — same rule as audio.

COVERS ARE THUMBNAILS FIRST. On the map a cover is a 30-60px disc that
grows on hover. The prompt therefore asks for one bold central subject
and a calm background — a busy wide shot turns to mud at that size.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

import generate_story_images as gsi  # same directory; shared helpers

COVER_ASPECT = "1:1"       # topic discs are round; a square crops cleanly
COVER_MAX_PX = 800         # plenty for a hover-grown disc, small on the wire

COVER_INSTRUCTIONS = """You are the art director for a children's picture-book series.
You will be given one branching story. Choose the single moment that belongs on
its COVER: the image a child would point at and say "that one!".

Return EXACTLY this JSON shape and nothing else:

{
  "scene": "One or two sentences. One bold central subject, physically doing
            something from the story, close enough to fill the frame. A calm,
            simple background. This image must read clearly as a small round
            thumbnail.",
  "mood": "The feeling on the subject's face and in its posture — inviting,
           curious, warm. Include explicit negatives where a feeling could be
           misread."
}

RULES
- One subject, one moment. No collages, no montages, no split frames.
- Describe only what is visible. Never invent a character the story does not contain.
- Never describe text, signage, labels or speech bubbles.
- Never state a countable quantity of anything.
"""


def build_cover_prompt(story: dict, style: str) -> str:
    """Mood, scene, then the same verbatim anchors the scene images use."""
    art = gsi.art_for(story)
    cd = story.get("cover_direction") or {}
    parts = []
    if cd.get("mood"):
        parts.append(f"CHARACTER EXPRESSION AND BODY LANGUAGE: {cd['mood']}")
    if cd.get("scene"):
        parts.append(f"SCENE: {gsi.resolve_slots(cd['scene'], story)}")
    if art.get("anchor"):
        parts.append(f"SETTING: {art['anchor']}")
    if art.get("cast"):
        parts.append(f"CHARACTERS: {art['cast']}")
    parts += [
        f"STYLE: {style}",
        gsi.TELLER_FRAMING.get(story.get("teller", ""), ""),
        "COMPOSITION: a children's book COVER — one bold central subject "
        "filling most of a square frame, simple uncluttered background, "
        "strong silhouette, readable even as a small round thumbnail.",
        f"CONSTRAINTS: render no text of any kind — no title, words, letters, "
        f"numbers, labels, signage, speech bubbles or captions. {gsi.NO_COUNTS}",
    ]
    return "\n\n".join(x for x in parts if x)


def derive_cover_direction(story: dict, model: str, project: str,
                           location: str, style: str) -> dict:
    """One text call: the story in, one drawable cover moment out."""
    import re
    from google import genai
    from google.genai import types
    client = genai.Client(vertexai=True, project=project, location=location)
    prompt = step_one_payload(story, style)
    last = None
    for m in ([model] if model else gsi.TEXT_MODELS):
        try:
            resp = client.models.generate_content(
                model=m, contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", temperature=0.4))
        except Exception as e:
            last = e
            continue
        raw = (resp.text or "").strip()
        try:
            cd = json.loads(raw)
        except json.JSONDecodeError:
            mm = re.search(r"\{.*\}", raw, re.S)
            if not mm:
                last = ValueError(f"{m} returned no JSON")
                continue
            cd = json.loads(mm.group(0))
        cd["derived_by"] = m
        return cd
    raise RuntimeError(f"could not derive cover direction: {last}")


def step_one_payload(story: dict, style: str) -> str:
    """The exact text sent to the art-direction model — printable for review."""
    art = gsi.art_for(story)
    roles = [c.get("role", "") for c in (story.get("build_record") or {}).get("cast", [])]
    body = {
        "title": story.get("title"),
        "age_band": story.get("age_band"),
        "topic": (story.get("topics") or {}).get("knowledge_domain"),
        "teller": story.get("teller"),
        "tone": story.get("tone"),
        "cast_roles_from_build_record": roles,
        "existing_art_direction_cast": art.get("cast") or "",
        "first_segment": gsi.resolve_slots(
            (story.get("segments") or [{}])[0].get("text", ""), story)[:600],
    }
    framing = gsi.TELLER_FRAMING.get(story.get("teller", ""), "")
    return (COVER_INSTRUCTIONS
            + f"\n\nTELLER FRAMING (obey this):\n{framing}\n"
            + f"\nHOUSE STYLE the image will use (do not repeat it back):\n{style}\n"
            + "\nTHE STORY:\n" + json.dumps(body, ensure_ascii=False, indent=1))


def to_square_web(blob: bytes, dest: Path) -> Path:
    """Centre-crop to square, downscale, webp. The map crops to a circle, so
    anything outside the centre square would never be seen anyway."""
    try:
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(blob)).convert("RGB")
        side = min(im.width, im.height)
        left = (im.width - side) // 2
        top = (im.height - side) // 2
        im = im.crop((left, top, left + side, top + side))
        if side > COVER_MAX_PX:
            im = im.resize((COVER_MAX_PX, COVER_MAX_PX), Image.LANCZOS)
        web = dest.with_suffix(".webp")
        im.save(web, "WEBP", quality=gsi.WEB_QUALITY, method=6)
        return web
    except ImportError:
        dest.write_bytes(blob)
        print("    (pillow not installed — wrote the raw image; the site "
              "expects .webp, so pip install pillow and re-run)")
        return dest


def website_paths(root: Path, a) -> tuple[Path, Path]:
    """Cover dir + manifest in the sibling buju_website repo (overridable)."""
    site = Path(a.site).resolve() if a.site else root.parent / "buju_website"
    if not (site / "pilot").is_dir():
        raise SystemExit(
            f"buju_website not found at {site} — pass --site /path/to/buju_website")
    return site / "pilot" / "img" / "covers", site / "pilot" / "data" / "covers.json"


def update_manifest(manifest: Path, story_id: str) -> None:
    """covers.json is {story_id: true, ...} — json in, json out, no splicing."""
    entries: dict = {}
    if manifest.is_file():
        entries = json.loads(manifest.read_text(encoding="utf-8"))
    entries[story_id] = True
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(dict(sorted(entries.items())), indent=1) + "\n",
        encoding="utf-8")


def do_story(story_path: Path, a, style: str, cover_dir: Path, manifest: Path) -> int:
    story = json.loads(story_path.read_text())
    sid = story["id"]
    print(f"\n{sid}")

    if a.prompt_only:
        print("\n--- step 1: exact payload for the cover-direction call ---\n")
        print(step_one_payload(story, style))
        if story.get("cover_direction"):
            print("\n--- step 2: exact image prompt (from stored cover_direction) ---\n")
            print(build_cover_prompt(story, style))
        else:
            print("\n(no cover_direction stored yet — the step-2 prompt appears "
                  "here after --direction-only or a full run)")
        return 0

    if a.force or not story.get("cover_direction"):
        print(f"  deriving cover direction ({a.text_model or gsi.TEXT_MODELS[0]}) ...")
        story["cover_direction"] = derive_cover_direction(
            story, a.text_model, a.project, a.location, style)
        story_path.write_text(
            json.dumps(story, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"  cover_direction written onto {story_path.name} "
              f"(via {story['cover_direction'].get('derived_by')})")
    else:
        print("  using stored cover_direction (pass --force to re-derive)")

    if a.direction_only:
        print("\n--- cover direction (edit it on the story file, then rerun) ---\n")
        print(json.dumps({k: v for k, v in story["cover_direction"].items()
                          if k != "derived_by"}, ensure_ascii=False, indent=1))
        return 0

    dest = cover_dir / f"{sid}.png"
    web = dest.with_suffix(".webp")
    if web.exists() and not a.force:
        print(f"  {web.name} already exists (pass --force to redo)")
        return 0
    prompt = build_cover_prompt(story, style)
    print(f"  generating cover ({a.model}) ...")
    # The shared generate() reads the aspect ratio from the illustrator's
    # module global — set it for covers, restore after. Ugly, but it keeps
    # one image path instead of two.
    prev_aspect = gsi.ASPECT
    gsi.ASPECT = COVER_ASPECT
    try:
        blobs = gsi.generate(prompt, a.model, a.project, a.location)
    finally:
        gsi.ASPECT = prev_aspect
    if not blobs:
        print("  ! model returned no image")
        return 1
    cover_dir.mkdir(parents=True, exist_ok=True)
    out = to_square_web(blobs[0], dest)
    update_manifest(manifest, sid)
    print(f"  wrote {out} and listed it in {manifest.name}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--story", help="full path to one story json")
    ap.add_argument("--stories", nargs="+", default=[],
                    help="substring match on story filenames")
    ap.add_argument("--prompt-only", action="store_true",
                    help="print the exact prompts, call nothing, spend nothing")
    ap.add_argument("--direction-only", action="store_true",
                    help="run step 1 only (one text call), print the result")
    ap.add_argument("--force", action="store_true",
                    help="re-derive the direction and redo an existing cover")
    ap.add_argument("--site", help="path to the buju_website repo "
                                   "(default: sibling of this repo)")
    ap.add_argument("--model", default=gsi.DEFAULT_MODEL)
    ap.add_argument("--text-model", default=None,
                    help=f"cover-direction model; default tries {gsi.TEXT_MODELS}")
    ap.add_argument("--project", default=gsi.DEFAULT_PROJECT)
    ap.add_argument("--location", default=gsi.DEFAULT_LOCATION)
    a = ap.parse_args()
    a.all = False   # select() checks it; covers are always named explicitly

    root = gsi.find_root(Path(__file__))
    style = gsi.load_style(root)
    picked = gsi.select(root, a)
    if not picked:
        print("Nothing selected. Name stories with --stories or --story — "
              "there is deliberately no --all for image generation.")
        return 1
    cover_dir, manifest = website_paths(root, a)
    rc = 0
    for p in picked:
        rc |= do_story(p, a, style, cover_dir, manifest)
    if not a.prompt_only and not a.direction_only:
        print("\nLOOK AT THE IMAGES before committing — same rule as audio.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
