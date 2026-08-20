#!/usr/bin/env python3
"""Generate one scene illustration per segment of a course story.

Run from the repo root as a script (never `python -m`, never PYTHONPATH=.):

    python scripts/generate_story_images.py --story <path/to/story.json> --dry-run
    python scripts/generate_story_images.py --story <path/to/story.json>
    python scripts/generate_story_images.py --story <path> --only s3 --force

WHY VERTEX. You already have GCP credits, the `buju-backend` project,
and ADC configured for the Gemini->Vertex migration. Imagen bills to those
credits and needs no new vendor, no new key, and no new compliance review.
The alternative (OpenAI image models) is a separate account and separate
billing for no benefit here.

CHARACTER CONSISTENCY is the hard part of illustrating a recurring cast.
This script does the cheap version that works: every prompt repeats the same
verbatim STYLE and CAST blocks, which live on the story under
`course.art_direction`. Same words in, similar faces out. It is not perfect.
When the cast is settled, upgrade to Imagen's subject-reference feature by
passing 2-3 approved reference images per character.

Output lands in preview/course_images/<story_id>/<segment>.png (gitignored),
and the path is written back onto each segment as `image`. Look at them
before anything reaches a child - same rule as audio.
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


def resolve_slots(text: str, story: dict) -> str:
    """Substitute {slot} with its default. Without this the fallback path ships
    a literal '{friend_name}' to the model, which degrades the scene."""
    slots = story.get("slots", {})
    return re.sub(r"\{(\w+)\}",
                  lambda m: slots.get(m.group(1), {}).get("default", m.group(0)), text)


def build_prompt(seg: dict, story: dict) -> str:
    """Emotion first, then scene, then the three verbatim anchors.

    Expression and posture lead because in an SEL story they are the lesson,
    not decoration: the child reads the feeling off the face before the words.
    """
    art = story.get("course", {}).get("art_direction", {})
    if seg.get("illustration_prompt"):
        return resolve_slots(seg["illustration_prompt"], story)
    mood = seg.get("emotion_cue") or ""
    scene = resolve_slots(seg.get("text", ""), story)[:300]
    parts = []
    if mood:
        parts.append(f"CHARACTER EXPRESSION AND BODY LANGUAGE: {mood}")
    parts += [f"SCENE: {scene}",
              art.get("anchor", ""),
              f"CHARACTERS: {art.get('cast','')}",
              f"STYLE: {art.get('style','')}",
              "COMPOSITION: eye-level storybook framing, the characters' faces "
              "clearly readable.",
              "CONSTRAINTS: render no text of any kind — no words, letters, "
              "numbers, labels, signage, speech bubbles or captions."]
    return "\n\n".join(x for x in parts if x)


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--story")
    ap.add_argument("--out", default=None, help="default: preview/course_images/<story_id>")
    ap.add_argument("--only", nargs="*", help="segment ids; default all")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--project", default=DEFAULT_PROJECT)
    ap.add_argument("--location", default=DEFAULT_LOCATION)
    ap.add_argument("--variants", type=int, default=1, help="images per segment, to pick from")
    ap.add_argument("--force", action="store_true", help="regenerate existing files")
    ap.add_argument("--dry-run", action="store_true", help="print prompts, call nothing")
    ap.add_argument("--probe", action="store_true",
                    help="find which Imagen model this project can call, then exit")
    a = ap.parse_args()

    if a.probe:
        return probe(a.project, None if a.location == DEFAULT_LOCATION else a.location)

    if not a.story:
        return print("need --story (or --probe)") or 1
    story_path = Path(a.story).resolve()
    story = json.loads(story_path.read_text())
    # datastore root = the ancestor holding story_definitions/, else the file's dir
    root = next((q for q in story_path.parents if (q / "story_definitions").is_dir()), story_path.parent)
    base = (root / "story_definitions") if (root / "story_definitions").is_dir() else root
    out_dir = Path(a.out) if a.out else base / "preview" / "course_images" / story["id"]
    out_dir.mkdir(parents=True, exist_ok=True)

    targets = [s for s in story["segments"] if not a.only or s["id"] in a.only]
    print(f"{story['title']}  ->  {out_dir}")
    print(f"model={a.model}  project={a.project}  location={a.location}  "
          f"segments={[s['id'] for s in targets]}\n")

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
        except Exception as e:                       # keep going; one bad scene is not a run
            print(f"  {seg['id']}: FAILED — {type(e).__name__}: {e}")
            if seg.get("image") and not (base / seg["image"]).exists():
                seg.pop("image")                     # don't leave a dangling path
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
                web = to_web(blob, p)
                seg["image"] = _rel(web, base)
                print(f"  {seg['id']}: {p.name} {len(blob)//1024} KB "
                      f"-> {web.name} {web.stat().st_size//1024} KB")
            else:
                print(f"  {seg['id']}: alt {p.name} ({len(blob)//1024} KB)")
        wrote += 1
        if seg is not targets[-1]:
            time.sleep(GAP_SECONDS)

    if not a.dry_run and wrote:
        story_path.write_text(json.dumps(story, indent=2, ensure_ascii=False))
        print(f"\n{wrote} scene(s) written; image paths saved onto the story.")
        print("LOOK AT THEM before publishing. Same gate as audio.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
