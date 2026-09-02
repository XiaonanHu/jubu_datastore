#!/usr/bin/env python3
"""Illustrate a story — one scene per segment. Works on COURSE and LIBRARY stories.

Run from the jubu_datastore repo root as a script (never `python -m`,
never PYTHONPATH=.):

    # which image model can this project call?
    python scripts/generate_story_images.py --probe

    # one story, by path or by id substring
    python scripts/generate_story_images.py --story story_definitions/stories/pilot/ants__age5to6__d1__authored__f72b04.json
    python scripts/generate_story_images.py --stories ants bees

    # derive and review the art direction WITHOUT spending image quota
    python scripts/generate_story_images.py --stories ants --art-only

    # a batch, newest quota rules apply — start small
    python scripts/generate_story_images.py --all --limit 3

    # redo one scene after editing the prompt
    python scripts/generate_story_images.py --stories ants --only s3 --force

TWO KINDS OF STORY, ONE PIPELINE.

  Course stories arrive with `course.art_direction` and a hand-written
  `illustration_prompt` per segment. Those are used verbatim.

  Library stories have neither. They do have `build_record.cast` — the roles
  the pipeline invented, with reasons — but roles are not pictures: "Mama Duck"
  says nothing about what to draw. So this script DERIVES an art direction in
  one text call per story: a visual CAST block, a scene ANCHOR, and a SCENE +
  MOOD line per segment. The result is written back onto the story as
  `art_direction` so it is reviewable, editable, and stable across reruns.

  One derivation call per story, not per scene, is the point. The six prompts
  then repeat the same CAST/ANCHOR/STYLE text verbatim, which is what keeps a
  character recognisable from scene to scene.

HOUSE STYLE is shared by every story in the library and lives in
`course_definitions/art_style.yaml`. One look for the whole shelf.

Output: preview/course_images/<story_id>/<segment>.webp, path written onto
each segment as `image`. LOOK AT THEM before publishing — same rule as audio.

WHY VERTEX. The GCP credits, the `buju-backend` project and ADC are already
set up from the Gemini migration. No new vendor, no new key, no new billing.

CHARACTER CONSISTENCY is the hard part. The cheap version that works: every
scene prompt repeats the same STYLE, CAST and ANCHOR text word for word. Same
words in, similar faces out. Not perfect. When the cast is settled, upgrade to
subject-reference images: 2-3 approved reference pictures per character.
"""
from __future__ import annotations
import argparse, base64, json, os, re, sys, time
from pathlib import Path

# IMAGEN IS GONE. As of 2026 the Imagen publisher models have been retired on
# Vertex; every imagen-* id now 404s in every region, and google-genai warns
# that generate_images() is deprecated. Image generation moved to the Gemini
# image models, called through generate_content() with an IMAGE response
# modality. That is what this script does.
#
# (Also: `gcloud ai models list` only ever showed YOUR Model Registry — models
# you uploaded or trained. Publisher models never appeared there, so "Listed 0
# items" was never evidence of anything. Use --probe; it calls the API.)
CANDIDATE_MODELS = [
    "gemini-3.1-flash-image",     # the documented Imagen replacement
    "gemini-3-pro-image",         # higher quality, higher cost
    "gemini-2.5-flash-image",     # older fallback
]
# Gemini image models are usually served from "global" on Vertex.
CANDIDATE_LOCATIONS = ["global", "us-central1", "us-east4"]
DEFAULT_MODEL = os.environ.get("BUJU_IMAGE_MODEL", CANDIDATE_MODELS[0])
DEFAULT_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "buju-backend")
DEFAULT_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")

ASPECT = "16:9"

# Free/new projects get a low per-minute image quota; a 6-scene run trips 429
# about halfway. Space the calls out and back off rather than losing scenes.
GAP_SECONDS = 8.0
RETRY_DELAYS = [15, 45, 90]

# Web delivery: a raw 1376x768 PNG is ~1.5 MB. Six of those is 9 MB of page.
# WebP at 1200px wide is ~10x smaller and indistinguishable at reading size.
WEB_MAX_WIDTH = 1200
WEB_QUALITY = 82

# One look for the whole library. Overridable in course_definitions/art_style.yaml.
DEFAULT_STYLE = ("Warm hand-painted children's picture-book illustration. Soft cream paper "
                 "background, gentle gouache texture, rounded friendly shapes, warm terracotta "
                 "and sage palette, soft even light, no harsh shadows. No text, no letters, "
                 "no numbers anywhere.")

# How each teller wants to be drawn. This is a real art decision, not a detail.
TELLER_FRAMING = {
    "we_adventure": (
        "The teller is 'we' — Buju and the listening child together. Do NOT draw a "
        "specific named protagonist child's face as the hero. Show the companion "
        "characters clearly and place 'us' as a child seen from behind or from the "
        "side at the edge of frame, so any child can be the one adventuring."),
    "named_hero": (
        "The teller is a named hero the listening child names. Draw the hero clearly "
        "and consistently, but never write their name anywhere in the image."),
    "storyteller_tale": (
        "The teller is a character recounting a memory. Draw the remembered scene "
        "itself, warmly lit, as the storyteller describes it."),
}

# Counts are a losing bet: image models cannot reliably render an exact number
# of things, and a picture that contradicts the text is worse than no picture.
NO_COUNTS = ("Do not depict any specific countable quantity of objects. Show 'some' or "
             "'a few'. Never try to match an exact number.")


def resolve_slots(text: str, story: dict) -> str:
    """Substitute {slot} with its default. Without this the fallback path ships
    a literal '{friend_name}' to the model, which degrades the scene."""
    slots = story.get("slots", {})
    return re.sub(r"\{(\w+)\}",
                  lambda m: slots.get(m.group(1), {}).get("default", m.group(0)), text)


def build_prompt(seg: dict, story: dict) -> str:
    """Mood first, then scene, then the three verbatim anchors.

    Expression and posture lead because in a children's story the feeling on the
    face is what a pre-reader actually reads. CAST, ANCHOR and STYLE are repeated
    word-for-word in every scene — that repetition is the only thing keeping a
    character recognisable from one picture to the next.
    """
    art = art_for(story)
    if seg.get("illustration_prompt"):                 # course: hand-written
        return resolve_slots(seg["illustration_prompt"], story)

    sc = (art.get("scenes") or {}).get(seg["id"]) or {}
    mood = sc.get("mood") or seg.get("emotion_cue") or ""
    scene = sc.get("scene") or resolve_slots(seg.get("text", ""), story)[:300]
    parts = []
    if mood:
        parts.append(f"CHARACTER EXPRESSION AND BODY LANGUAGE: {mood}")
    parts.append(f"SCENE: {resolve_slots(scene, story)}")
    if art.get("anchor"):
        parts.append(f"SETTING: {art['anchor']}")
    if art.get("cast"):
        parts.append(f"CHARACTERS: {art['cast']}")
    parts += [
              f"STYLE: {art.get('style') or DEFAULT_STYLE}",
              TELLER_FRAMING.get(story.get("teller", ""), ""),
              "COMPOSITION: eye-level storybook framing, the characters' faces "
              "clearly readable.",
              f"CONSTRAINTS: render no text of any kind — no words, letters, numbers, "
              f"labels, signage, speech bubbles or captions. {NO_COUNTS}"]
    return "\n\n".join(x for x in parts if x)


# ------------------------------------------------------- art direction (text)
TEXT_MODELS = ["gemini-3.1-flash", "gemini-3-flash", "gemini-2.5-flash"]

DERIVE_INSTRUCTIONS = """You are the art director for a children's picture-book series.
You will be given one branching story. Return JSON describing how to illustrate it.

Return EXACTLY this shape and nothing else:

{
  "cast": "One paragraph. Every character who appears more than once, each with
           concrete visual detail an illustrator could not get wrong: age, build,
           hair, clothing with colours, footwear. Name them as the story names them.",
  "anchor": "One paragraph. The setting and any recurring object that must look
             identical in every scene. Be specific about colours and materials.",
  "scenes": {
    "<segment id>": {
      "scene": "One or two sentences: what is physically happening, who is where,
                what their bodies are doing.",
      "mood": "The emotional state on the characters' faces and in their posture.
               Include explicit negatives where a feeling could be misread, e.g.
               'frustrated, NOT smiling, NOT playful'."
    }
  }
}

RULES
- Describe only what is visible. No plot explanation, no interpretation.
- Never invent a character the story does not contain.
- Never describe text, signage, labels or speech bubbles.
- Never state a countable quantity of anything.
- Faces and body language carry the story, so be precise about them.
"""


def derive_art_direction(story: dict, model: str, project: str, location: str,
                         style: str) -> dict:
    """One text call per story. Turns a story into a visual bible.

    Library stories record `build_record.cast` — roles and why they exist — but a
    role is not a picture. This converts roles into something drawable, once, so
    all six scenes can repeat it verbatim.
    """
    from google import genai
    from google.genai import types
    client = genai.Client(vertexai=True, project=project, location=location)

    slots = story.get("slots", {})
    fill = lambda s: re.sub(r"\{(\w+)\}",
                            lambda m: slots.get(m.group(1), {}).get("default", m.group(0)), s)
    roles = [c.get("role", "") for c in (story.get("build_record") or {}).get("cast", [])]
    body = {
        "title": story.get("title"),
        "age_band": story.get("age_band"),
        "topic": (story.get("topics") or {}).get("knowledge_domain"),
        "spine": story.get("spine"),
        "pattern": story.get("pattern"),
        "teller": story.get("teller"),
        "tone": story.get("tone"),
        "cast_roles_from_build_record": roles,
        "segments": {s["id"]: fill(s.get("text", "")) for s in story["segments"]},
    }
    framing = TELLER_FRAMING.get(story.get("teller", ""), "")
    prompt = (DERIVE_INSTRUCTIONS
              + f"\n\nTELLER FRAMING (obey this):\n{framing}\n"
              + f"\nHOUSE STYLE the images will use (do not repeat it back):\n{style}\n"
              + "\nTHE STORY:\n" + json.dumps(body, ensure_ascii=False, indent=1))

    last = None
    for m in ([model] if model else TEXT_MODELS):
        try:
            resp = client.models.generate_content(
                model=m, contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", temperature=0.4))
        except Exception as e:
            last = e; continue
        raw = (resp.text or "").strip()
        try:
            art = json.loads(raw)
        except json.JSONDecodeError:
            mm = re.search(r"\{.*\}", raw, re.S)
            if not mm:
                last = ValueError(f"{m} returned no JSON"); continue
            art = json.loads(mm.group(0))
        art["style"] = style
        art["derived_by"] = m
        return art
    raise RuntimeError(f"could not derive art direction: {last}")


def art_for(story: dict) -> dict:
    """Course stories bring their own; library stories use what we derived."""
    return (story.get("course") or {}).get("art_direction") or story.get("art_direction") or {}


def generate(prompt: str, model: str, project: str, location: str, n: int = 1):
    """Gemini image generation via generate_content.

    Returns a list of PNG/JPEG byte blobs. n>1 just calls n times: the image
    models return one image per request.
    """
    from google import genai
    from google.genai import types
    client = genai.Client(vertexai=True, project=project, location=location)

    def once() -> bytes | None:
        # image_config moved around between SDK builds; degrade rather than die.
        for cfg in _config_attempts(types):
            try:
                resp = client.models.generate_content(
                    model=model, contents=prompt, config=cfg)
            except TypeError:
                continue
            for cand in (resp.candidates or []):
                for part in (getattr(cand.content, "parts", None) or []):
                    blob = getattr(part, "inline_data", None)
                    if blob and getattr(blob, "data", None):
                        return blob.data
            return None
        return None

    out = []
    for _ in range(max(1, n)):
        b = None
        for attempt, delay in enumerate([0] + RETRY_DELAYS):
            if delay:
                print(f"    quota hit; waiting {delay}s "
                      f"(retry {attempt}/{len(RETRY_DELAYS)})")
                time.sleep(delay)
            try:
                b = once(); break
            except Exception as e:
                if "429" not in str(e) and "RESOURCE_EXHAUSTED" not in str(e):
                    raise
                if attempt == len(RETRY_DELAYS):
                    raise
        if b:
            out.append(b)
    return out


def to_web(blob: bytes, dest: Path) -> Path:
    """Downscale and re-encode for the page. Keeps the original PNG beside it."""
    try:
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(blob)).convert("RGB")
        if im.width > WEB_MAX_WIDTH:
            im = im.resize((WEB_MAX_WIDTH, round(im.height * WEB_MAX_WIDTH / im.width)),
                           Image.LANCZOS)
        web = dest.with_suffix(".webp")
        im.save(web, "WEBP", quality=WEB_QUALITY, method=6)
        return web
    except ImportError:
        print("    (pillow not installed — shipping the full-size PNG; "
              "pip install pillow to shrink it ~10x)")
        return dest


def _config_attempts(types):
    """Most specific config first, then progressively plainer ones."""
    tries = []
    try:
        tries.append(types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(aspect_ratio=ASPECT)))
    except Exception:
        pass
    try:
        tries.append(types.GenerateContentConfig(response_modalities=["IMAGE"]))
    except Exception:
        pass
    tries.append(None)
    return tries


def probe(project: str, location: str | None) -> int:
    """Try every (model, location) pair until one returns image bytes."""
    locs = [location] if location else CANDIDATE_LOCATIONS
    print(f"project={project}")
    print(f"models={CANDIDATE_MODELS}\nlocations={locs}\n")
    ok = []
    for loc in locs:
        for m in CANDIDATE_MODELS:
            label = f"{m} @ {loc}"
            try:
                imgs = generate("A single red wooden toy block on a plain cream "
                                "background, soft flat children's book illustration, "
                                "no text.", m, project, loc, 1)
            except Exception as e:
                msg = str(e).replace("\n", " ")
                short = "404 not found" if "404" in msg else msg[:100]
                print(f"  {label:38} {type(e).__name__}: {short}")
                continue
            if not imgs:
                print(f"  {label:38} call succeeded but returned no image "
                      f"(safety filter, or text-only response)")
                continue
            f = Path(f"probe_{m}_{loc}.png"); f.write_bytes(imgs[0])
            print(f"  {label:38} OK  {len(imgs[0])//1024} KB -> {f.name}")
            ok.append((m, loc))
    if ok:
        m, loc = ok[0]
        print(f"\nUse:\n  export BUJU_IMAGE_MODEL={m}\n  export GOOGLE_CLOUD_LOCATION={loc}")
        print("PNG samples written beside this script — look at them before a batch run.")
        return 0
    print("\nNothing worked. In order:")
    print(f"  1. gcloud services enable aiplatform.googleapis.com --project={project}")
    print("  2. gcloud auth application-default login")
    print("  3. grant YOUR user roles/aiplatform.user — a role on the Compute Engine")
    print("     default service account does not cover your ADC user credentials:")
    print(f"     gcloud projects add-iam-policy-binding {project} \\")
    print("       --member=user:$(gcloud config get-value account) --role=roles/aiplatform.user")
    print("  4. pip install -U google-genai")
    print("  5. confirm the current image model id at")
    print("     https://firebase.google.com/docs/ai-logic/imagen-models-migration")
    return 1


def _rel(p: Path, base: Path) -> str:
    try:
        return str(p.relative_to(base))
    except ValueError:
        return str(p)

# ------------------------------------------------------------ story selection
def find_root(p: Path) -> Path:
    """The datastore root: the nearest ancestor holding story_definitions/."""
    p = p.resolve()
    cands = [p] + list(p.parents) if p.is_dir() else list(p.parents)
    return next((q for q in cands if (q / "story_definitions").is_dir()), p)


def load_style(root: Path) -> str:
    """House style for the whole shelf, editable without touching this file."""
    f = root / "course_definitions" / "art_style.yaml"
    if not f.exists():
        return DEFAULT_STYLE
    try:
        import yaml
        return (yaml.safe_load(f.read_text()) or {}).get("style") or DEFAULT_STYLE
    except Exception as e:
        print(f"! could not read {f.name} ({e}); using the built-in style.")
        return DEFAULT_STYLE


def story_dirs(root: Path) -> list[Path]:
    base = root / "story_definitions" / "stories"
    return [d for d in (base / "pilot", base / "courses") if d.is_dir()]


def select(root: Path, a) -> list[Path]:
    """--story wins, then --stories (substring match), then --all."""
    if a.story:
        return [Path(a.story).resolve()]
    pool = sorted(f for d in story_dirs(root) for f in d.glob("*.json"))
    if a.stories:
        picked: list[Path] = []
        for q in a.stories:
            hits = [f for f in pool if q.lower() in f.name.lower()]
            if not hits:
                print(f"! no story matches '{q}'")
            elif len(hits) > 1 and not a.all:
                # Ambiguity is a stop, not a guess: silently illustrating the
                # wrong story burns image quota and looks like success.
                print(f"! '{q}' matches {len(hits)}: {[h.name for h in hits]}")
                print("  Narrow it, or pass the full path with --story.")
            else:
                picked += hits
        return picked
    if a.all:
        return pool[: a.limit] if a.limit else pool
    return []


# ------------------------------------------------------------------ one story
def do_story(story_path: Path, a, style: str) -> int:
    story = json.loads(story_path.read_text())
    root = find_root(story_path)
    base = (root / "story_definitions") if (root / "story_definitions").is_dir() else root
    out_dir = Path(a.out) if a.out else base / "preview" / "course_images" / story["id"]

    hand_written = any(s.get("illustration_prompt") for s in story["segments"])
    art = art_for(story)
    need_art = not hand_written and (a.redraw_art or not art.get("scenes"))

    print(f"\n=== {story['title']}  [{story['id']}]")
    if need_art:
        if a.dry_run:
            # Say so loudly: the prompts printed below fall back to raw segment
            # text, so they are NOT what a real run sends. Only --art-only
            # shows the real thing without spending image quota.
            print("  would derive art direction (1 text call) — SKIPPED in --dry-run,")
            print("  so the prompts below use raw segment text, not the real ones.")
            print("  Use --art-only to see the real art direction.")
        else:
            print(f"  deriving art direction ({a.text_model or TEXT_MODELS[0]}) ...")
            try:
                art = derive_art_direction(story, a.text_model, a.project,
                                           a.location, style)
            except Exception as e:
                print(f"  ! art direction FAILED — {type(e).__name__}: {e}")
                return 1
            story["art_direction"] = art
            story_path.write_text(json.dumps(story, indent=2, ensure_ascii=False))
            print(f"  art direction saved onto the story "
                  f"({len(art.get('scenes') or {})} scenes, via {art.get('derived_by')})")
    if a.art_only:
        if art:
            print(f"\n  CAST: {art.get('cast','')}\n\n  ANCHOR: {art.get('anchor','')}")
            for sid, sc in (art.get("scenes") or {}).items():
                print(f"\n  [{sid}] {sc.get('scene','')}\n        mood: {sc.get('mood','')}")
        print("\n  --art-only: no images generated. Edit `art_direction` on the "
              "story, then rerun without --art-only.")
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    targets = [s for s in story["segments"] if not a.only or s["id"] in a.only]
    print(f"  -> {out_dir}")
    print(f"  model={a.model}  segments={[s['id'] for s in targets]}")

    wrote = 0
    for seg in targets:
        prompt = build_prompt(seg, story)
        dest = out_dir / f"{seg['id']}.png"
        web = dest.with_suffix(".webp")
        have = web if web.exists() else (dest if dest.exists() else None)
        if have and not a.force and not a.dry_run:
            print(f"  {seg['id']}: exists, skipping (use --force)")
            seg["image"] = _rel(have, base)
            continue
        if a.dry_run:
            print(f"--- {seg['id']} ---\n{prompt}\n")
            continue
        try:
            images = generate(prompt, a.model, a.project, a.location, a.variants)
        except Exception as e:                   # keep going; one bad scene is not a run
            print(f"  {seg['id']}: FAILED — {type(e).__name__}: {e}")
            if seg.get("image") and not (base / seg["image"]).exists():
                seg.pop("image")                 # don't leave a dangling path
            continue
        if not images:
            print(f"  {seg['id']}: no image returned (safety filter?)")
            if seg.get("image") and not (base / seg["image"]).exists():
                seg.pop("image")
            continue
        for k, blob in enumerate(images):
            p = dest if k == 0 else out_dir / f"{seg['id']}_alt{k}.png"
            p.write_bytes(blob)
            if k == 0:
                w = to_web(blob, p)
                seg["image"] = _rel(w, base)
                print(f"  {seg['id']}: {p.name} {len(blob)//1024} KB "
                      f"-> {w.name} {w.stat().st_size//1024} KB")
            else:
                print(f"  {seg['id']}: alt {p.name} ({len(blob)//1024} KB)")
        wrote += 1
        if seg is not targets[-1]:
            time.sleep(GAP_SECONDS)

    if not a.dry_run and (wrote or need_art):
        story_path.write_text(json.dumps(story, indent=2, ensure_ascii=False))
    if wrote:
        print(f"  {wrote} scene(s) written; image paths saved onto the story.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Illustrate course and library stories. One scene per segment.")
    ap.add_argument("--story", help="path to one story JSON")
    ap.add_argument("--stories", nargs="*", metavar="MATCH",
                    help="story id substrings, e.g. --stories ants bees")
    ap.add_argument("--all", action="store_true", help="every story under stories/")
    ap.add_argument("--limit", type=int, default=0, help="cap --all; quota is finite")
    ap.add_argument("--root", default=".", help="jubu_datastore checkout (default: cwd)")
    ap.add_argument("--out", default=None, help="default: preview/course_images/<story_id>")
    ap.add_argument("--only", nargs="*", help="segment ids; default all")
    ap.add_argument("--art-only", action="store_true",
                    help="derive and print the art direction, generate no images")
    ap.add_argument("--redraw-art", action="store_true",
                    help="re-derive art direction even if the story already has one")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--text-model", default=None,
                    help=f"art-direction model; default tries {TEXT_MODELS}")
    ap.add_argument("--project", default=DEFAULT_PROJECT)
    ap.add_argument("--location", default=DEFAULT_LOCATION)
    ap.add_argument("--variants", type=int, default=1, help="images per segment, to pick from")
    ap.add_argument("--force", action="store_true", help="regenerate existing files")
    ap.add_argument("--dry-run", action="store_true", help="print prompts, call nothing")
    ap.add_argument("--probe", action="store_true",
                    help="find which image model this project can call, then exit")
    a = ap.parse_args()

    if a.probe:
        return probe(a.project, None if a.location == DEFAULT_LOCATION else a.location)

    root = find_root(Path(a.story) if a.story else Path(a.root))
    paths = select(root, a)
    if not paths:
        print("nothing selected. Use --story PATH, --stories ants bees, or --all "
              "(with --limit).")
        return 1

    style = load_style(root)
    print(f"{len(paths)} story(ies)  project={a.project}  location={a.location}")
    if len(paths) > 3 and not a.dry_run and not a.art_only:
        # Six scenes a story, eight seconds apart, plus 429 backoff. A careless
        # --all is an hour of wall clock and a real bill.
        print(f"! {len(paths)} stories is ~{len(paths)*6} image calls. "
              f"Ctrl-C now if that was not deliberate.")
        time.sleep(5)

    bad = [p.name for p in paths if do_story(p, a, style) != 0]
    if not a.dry_run and not a.art_only:
        print("\nLOOK AT THE IMAGES before publishing. Same gate as audio.")
    if bad:
        print(f"\n! {len(bad)} story(ies) failed: {bad}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
