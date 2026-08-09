"""Batch-generate per-segment narration mp3s for pilot stories via Cartesia.

Run from the repo root (same rules as the other scripts — plain
`python scripts/generate_story_audio.py`, never `python -m`, never
PYTHONPATH=.). Needs CARTESIA_API_KEY: from the environment if exported,
otherwise read from the sibling jubu_backend repo's .env.local / .env
(same variable jubu_backend uses; the minimal /tts/bytes client below
follows jubu_backend/speech_services/text_to_speech/providers/
cartesia_tts.py). NEVER hardcode the key in this file — it is tracked
by git.

Unit of audio = one paragraph chunk of one segment (see
story_audio_chunks.py). Every chunk is generated with slot DEFAULTS
substituted; chunks that contain a slot are re-voiced live at read time
with the child's chosen name (buju_website/api/pilot-name-audio.js), and
the default-value mp3 generated here is their fallback.

Voice per story = the story's `teller` mapped through
story_definitions/audio_voices.json. Audition voices before any batch run:

    python scripts/generate_story_audio.py --audition <voice_id> [<voice_id>…]
        one short sample per (teller, candidate voice) into
        story_definitions/preview/audio_auditions/ — listen, then put the
        winners into audio_voices.json.

    python scripts/generate_story_audio.py --stories mars.age5to6 bees
        voice only stories whose id contains one of the given substrings.

    python scripts/generate_story_audio.py --all
        voice the whole library. Deliberately a separate flag: do NOT run
        this before voice samples are approved (cost + story churn).

Idempotent: existing mp3s are skipped (--force regenerates). Every run
logs characters sent to Cartesia, the cost driver.

Outputs:
    <site_audio_dir>/<story_id>/<segment_or_choice_id>_<chunk_index>.mp3
        default: story_definitions/preview/pilot_audio (local review copies;
        --upload rsyncs them to the private gs://buju-pilot-audio bucket the
        site serves from — listen BEFORE uploading, that's the QA gate)
    story_definitions/audio_manifest.json
        {story_id: {voice_id, model_id, segments: {seg_id: [
            {"i": 0, "file": "s1_00.mp3", "has_slot": false, "chars": 123}]}}}
        merged across runs; build_pilot_site.py stamps it into stories.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

import build_story_explorer as bse  # same directory; reuse loader + validator
import story_audio_chunks

REPO_ROOT = Path(__file__).resolve().parent.parent
VOICE_CONFIG_PATH = REPO_ROOT / "story_definitions" / "audio_voices.json"
MANIFEST_PATH = REPO_ROOT / "story_definitions" / "audio_manifest.json"
AUDITION_DIR = REPO_ROOT / "story_definitions" / "preview" / "audio_auditions"
# Local clips land here for review-by-ear, then --upload rsyncs them to the
# private GCS bucket the site serves from (api/pilot-audio.js signs URLs).
# Deliberately NOT inside buju_website anymore, so mp3s can't sneak into
# that repo's git history.
DEFAULT_SITE_AUDIO_DIR = REPO_ROOT / "story_definitions" / "preview" / "pilot_audio"
DEFAULT_AUDIO_BUCKET = "buju-pilot-audio"  # override with BUJU_PILOT_AUDIO_BUCKET

CARTESIA_TTS_BYTES_URL = "https://api.cartesia.ai/tts/bytes"
# Must match the Cartesia-Version jubu_backend pins (see cartesia_tts.py).
CARTESIA_API_VERSION = "2026-03-01"
# Speech-only clips for phone playback: mp3 keeps files ~10x smaller than
# wav; 44.1 kHz / 96 kbps is transparent for a single voice.
MP3_OUTPUT_FORMAT = {"container": "mp3", "sample_rate": 44100, "bit_rate": 96000}
# How many paragraphs of a story's opening segment an audition sample uses —
# enough to judge a voice, short enough to stay cheap across candidates.
AUDITION_PARAGRAPH_COUNT = 2


def load_voice_config() -> dict[str, Any]:
    if not VOICE_CONFIG_PATH.is_file():
        raise SystemExit(f"missing voice config: {VOICE_CONFIG_PATH}")
    with open(VOICE_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def voice_for_story(story: dict[str, Any], voice_config: dict[str, Any]) -> dict[str, Any]:
    teller = story.get("teller")
    teller_voices = voice_config["tellers"]
    if teller not in teller_voices:
        raise SystemExit(
            f"story {story['id']} has teller '{teller}' with no entry in "
            f"{VOICE_CONFIG_PATH.name} — add one before generating"
        )
    return teller_voices[teller]


# Where to look for CARTESIA_API_KEY when it isn't exported: the sibling
# backend repo's env files (the key already lives there; keeping it in ONE
# place means it can never leak into this repo's git history).
BACKEND_ENV_FILES = [
    REPO_ROOT.parent / "jubu_backend" / ".env.local",
    REPO_ROOT.parent / "jubu_backend" / ".env",
]


def resolve_cartesia_api_key() -> str:
    api_key = os.getenv("CARTESIA_API_KEY")
    if api_key:
        return api_key
    for env_file in BACKEND_ENV_FILES:
        if not env_file.is_file():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("CARTESIA_API_KEY="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    print(f"using CARTESIA_API_KEY from {env_file}")
                    return value
    raise SystemExit(
        "CARTESIA_API_KEY not found: export it, or keep it in "
        f"{BACKEND_ENV_FILES[0]} / {BACKEND_ENV_FILES[1]} (do NOT hardcode "
        "it in this script — this file is tracked by git)."
    )


class CartesiaBatchClient:
    """Minimal /tts/bytes client (mirrors jubu_backend's CartesiaSpeaker
    auth: Bearer key + Cartesia-Version header)."""

    def __init__(self) -> None:
        api_key = resolve_cartesia_api_key()
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Cartesia-Version": CARTESIA_API_VERSION,
            }
        )

    def synthesize_mp3(
        self, text: str, voice_id: str, model_id: str, speed: float
    ) -> bytes:
        response = self._session.post(
            CARTESIA_TTS_BYTES_URL,
            json={
                "model_id": model_id,
                "transcript": text,
                "voice": {"mode": "id", "id": voice_id},
                "language": "en",
                "output_format": MP3_OUTPUT_FORMAT,
                "generation_config": {"speed": speed},
            },
            timeout=120,
        )
        response.raise_for_status()
        return response.content


def narration_units(story: dict[str, Any]) -> list[tuple[str, str]]:
    """(unit_id, prose) pairs to voice: every segment, then every
    tap-choice question — each becomes one or more paragraph chunks."""
    units = [(segment["id"], segment["text"]) for segment in story["segments"]]
    units.extend(
        (choice_point["id"], choice_point["question"])
        for choice_point in story["choice_points"]
    )
    return units


def generate_story(
    story: dict[str, Any],
    client: CartesiaBatchClient,
    voice_config: dict[str, Any],
    site_audio_dir: Path,
    force: bool,
) -> tuple[dict[str, Any], int, int]:
    """Generate all chunks for one story. Returns (manifest_entry,
    chars_sent, files_written)."""
    voice = voice_for_story(story, voice_config)
    voice_id = voice["voice_id"]
    speed = float(voice.get("speed", 1.0))
    model_id = voice_config["model_id"]
    slots = story.get("slots") or {}

    story_dir = site_audio_dir / story["id"]
    story_dir.mkdir(parents=True, exist_ok=True)

    manifest_segments: dict[str, list[dict[str, Any]]] = {}
    chars_sent = 0
    files_written = 0
    for unit_id, prose in narration_units(story):
        chunk_entries: list[dict[str, Any]] = []
        for index, chunk_text in enumerate(story_audio_chunks.paragraph_chunks(prose)):
            slot_tokens = story_audio_chunks.declared_slot_tokens(chunk_text, slots)
            spoken_text = story_audio_chunks.substitute_slot_values(
                chunk_text, slots, {}
            )
            file_name = f"{unit_id}_{index:02d}.mp3"
            file_path = story_dir / file_name
            if force or not file_path.is_file():
                started = time.monotonic()
                file_path.write_bytes(
                    client.synthesize_mp3(spoken_text, voice_id, model_id, speed)
                )
                chars_sent += len(spoken_text)
                files_written += 1
                print(
                    f"  {story['id']}/{file_name}: {len(spoken_text)} chars "
                    f"in {time.monotonic() - started:.1f}s"
                )
            chunk_entries.append(
                {
                    "i": index,
                    "file": file_name,
                    "has_slot": bool(slot_tokens),
                    "chars": len(spoken_text),
                }
            )
        manifest_segments[unit_id] = chunk_entries
    manifest_entry = {
        "voice_id": voice_id,
        "model_id": model_id,
        "speed": speed,
        "segments": manifest_segments,
    }
    return manifest_entry, chars_sent, files_written


def run_audition(candidate_voice_ids: list[str], voice_config: dict[str, Any]) -> int:
    """One short sample per (teller, candidate voice) so Xia can pick the
    voice mapping by ear before any batch run."""
    client = CartesiaBatchClient()
    stories = bse.load_stories()
    story_by_teller: dict[str, dict[str, Any]] = {}
    for story in sorted(stories, key=lambda s: s["id"]):
        story_by_teller.setdefault(story["teller"], story)
    AUDITION_DIR.mkdir(parents=True, exist_ok=True)
    chars_sent = 0
    for teller, story in sorted(story_by_teller.items()):
        opening_segment = next(
            segment
            for segment in story["segments"]
            if segment["id"] == story["start_segment"]
        )
        sample_paragraphs = story_audio_chunks.paragraph_chunks(
            opening_segment["text"]
        )[:AUDITION_PARAGRAPH_COUNT]
        sample_text = story_audio_chunks.substitute_slot_values(
            " ".join(sample_paragraphs), story.get("slots") or {}, {}
        )
        for voice_id in candidate_voice_ids:
            out_path = AUDITION_DIR / f"{teller}__{voice_id}.mp3"
            out_path.write_bytes(
                client.synthesize_mp3(
                    sample_text, voice_id, voice_config["model_id"], 1.0
                )
            )
            chars_sent += len(sample_text)
            print(f"wrote {out_path.relative_to(REPO_ROOT)}")
    print(
        f"\nauditions done ({chars_sent} chars sent). Listen, then set the "
        f"winning voice_id per teller in {VOICE_CONFIG_PATH.relative_to(REPO_ROOT)}"
    )
    return 0


def upload_stories_to_bucket(site_audio_dir: Path, story_ids: list[str]) -> None:
    """rsync each voiced story's clips to the private serving bucket via the
    gcloud CLI (uses your logged-in gcloud auth; no extra Python deps)."""
    import subprocess

    bucket = os.getenv("BUJU_PILOT_AUDIO_BUCKET", DEFAULT_AUDIO_BUCKET)
    for story_id in story_ids:
        story_dir = site_audio_dir / story_id
        destination = f"gs://{bucket}/{story_id}"
        print(f"uploading {story_id} -> {destination}")
        try:
            subprocess.run(
                ["gcloud", "storage", "rsync", str(story_dir), destination],
                check=True,
            )
        except FileNotFoundError:
            raise SystemExit(
                "gcloud CLI not found — install the Google Cloud SDK or run "
                f"manually: gcloud storage rsync {story_dir} {destination}"
            )
        except subprocess.CalledProcessError as error:
            raise SystemExit(
                f"upload failed for {story_id} (exit {error.returncode}); "
                "clips are still on disk — fix gcloud auth/bucket and re-run "
                "with --upload"
            )


def merge_manifest(new_entries: dict[str, Any]) -> None:
    manifest: dict[str, Any] = {}
    if MANIFEST_PATH.is_file():
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            manifest = json.load(f)
    manifest.update(new_entries)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stories", nargs="+", metavar="ID_SUBSTRING",
                        help="voice stories whose id contains any given substring")
    parser.add_argument("--all", action="store_true",
                        help="voice the whole library (only after samples are approved)")
    parser.add_argument("--audition", nargs="+", metavar="VOICE_ID",
                        help="generate teller samples for candidate voice ids")
    parser.add_argument("--force", action="store_true",
                        help="regenerate mp3s that already exist")
    parser.add_argument("--upload", action="store_true",
                        help="after generating, rsync each story's clips to "
                             "the serving bucket (gcloud auth required)")
    parser.add_argument("--site-audio-dir", type=Path, default=DEFAULT_SITE_AUDIO_DIR,
                        help=f"where mp3s land locally (default: {DEFAULT_SITE_AUDIO_DIR})")
    args = parser.parse_args()

    voice_config = load_voice_config()
    if args.audition:
        return run_audition(args.audition, voice_config)
    if not args.stories and not args.all:
        parser.error("pick stories with --stories, or use --all / --audition")

    stories = bse.load_stories()
    if args.stories:
        stories = [
            story
            for story in stories
            if any(substring in story["id"] for substring in args.stories)
        ]
        if not stories:
            raise SystemExit(f"no story ids match {args.stories}")

    client = CartesiaBatchClient()
    new_manifest_entries: dict[str, Any] = {}
    total_chars = 0
    total_files = 0
    for story in sorted(stories, key=lambda s: s["id"]):
        print(f"{story['id']} ({story['teller']}):")
        manifest_entry, chars_sent, files_written = generate_story(
            story, client, voice_config, args.site_audio_dir, args.force
        )
        new_manifest_entries[story["id"]] = manifest_entry
        total_chars += chars_sent
        total_files += files_written

    merge_manifest(new_manifest_entries)
    print(
        f"\ndone: {len(new_manifest_entries)} stories, {total_files} new mp3s, "
        f"{total_chars} chars sent to Cartesia (its cost driver; 0 chars = all "
        f"clips already existed). Manifest: {MANIFEST_PATH.relative_to(REPO_ROOT)}"
    )
    if args.upload:
        upload_stories_to_bucket(args.site_audio_dir, sorted(new_manifest_entries))
    else:
        print(
            "NOT uploaded — listen to the clips locally, then re-run the same "
            "command with --upload to push them to the serving bucket."
        )
    print(
        "Next: python scripts/build_pilot_site.py  (stamps audio info into "
        "stories.json), then copy stories.json to buju_website per PILOT_DEPLOY.md"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
