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
DIAGNOSE_DIR = REPO_ROOT / "story_definitions" / "preview" / "audio_diagnose"
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
DEFAULT_MP3_BIT_RATE = 128000  # override with "mp3_bit_rate" in audio_voices.json
WAV_OUTPUT_FORMAT = {"container": "wav", "encoding": "pcm_s16le", "sample_rate": 44100}


def mp3_format(bit_rate: int) -> dict[str, Any]:
    return {"container": "mp3", "sample_rate": 44100, "bit_rate": int(bit_rate)}
# How many paragraphs of a story's opening segment an audition sample uses —
# enough to judge a voice, short enough to stay cheap across candidates.
AUDITION_PARAGRAPH_COUNT = 2


def load_voice_config() -> dict[str, Any]:
    if not VOICE_CONFIG_PATH.is_file():
        raise SystemExit(f"missing voice config: {VOICE_CONFIG_PATH}")
    with open(VOICE_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def voice_for_story(
    story: dict[str, Any], voice_config: dict[str, Any], lang: str = "en"
) -> dict[str, Any]:
    """Resolve the full delivery settings for one story.

    Voice + speed come from the story's `teller`; the emotion that makes
    delivery animated comes from its `tone.dominant` (a per-teller
    "emotion" key wins if set). Sentence pacing is global unless the teller
    overrides it.
    """
    teller = story.get("teller")
    teller_voices = voice_config["tellers"]
    if teller not in teller_voices:
        raise SystemExit(
            f"story {story['id']} has teller '{teller}' with no entry in "
            f"{VOICE_CONFIG_PATH.name} — add one before generating"
        )
    teller_voice = teller_voices[teller]
    band_settings = (voice_config.get("age_bands") or {}).get(story.get("age_band"), {})
    lang_settings = (voice_config.get("languages") or {}).get(lang, {})
    if lang != "en" and not lang_settings:
        raise SystemExit(
            f"no voice configured for language '{lang}' — add it under "
            f"`languages` in {VOICE_CONFIG_PATH.name}"
        )

    def resolve(key: str, fallback: Any) -> Any:
        # Language wins for voice: teller is about WHO is telling the story,
        # not what language they speak, so a Hindi narration uses the Hindi
        # voice whatever the teller says. Pace still resolves by band.
        if key in lang_settings:
            return lang_settings[key]
        # Age band next: "for the little ones, read it like THIS" is the more
        # specific intent than "this kind of teller sounds like this".
        if key in band_settings:
            return band_settings[key]
        if key in teller_voice:
            return teller_voice[key]
        return voice_config.get(key, fallback)

    tone = (story.get("tone") or {}).get("dominant")
    emotion = None
    if voice_config.get("emotions_enabled", True):
        emotion = resolve("emotion", None) or (
            voice_config.get("tone_emotions") or {}
        ).get(tone)
    return {
        "voice_id": resolve("voice_id", None),
        "speed": float(resolve("speed", 1.0)),
        "emotion": emotion,
        "sentence_pause_ms": int(resolve("sentence_pause_ms", 0)),
    }


# Delivery settings baked into every clip. When these change, existing mp3s
# are stale and must be regenerated with --force — the script says so
# rather than silently leaving a half-updated library.
BAKED_IN_SETTINGS = (
    "voice_id", "model_id", "speed", "emotion", "sentence_pause_ms", "mp3_bit_rate",
)


def settings_drift(manifest_entry: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """Names of baked-in settings that differ from the clips on disk."""
    return [
        key
        for key in BAKED_IN_SETTINGS
        if manifest_entry.get(key) != current.get(key)
    ]


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

    def _post_with_retry(self, payload: dict[str, Any], attempts: int = 4):
        """POST to Cartesia, retrying transient failures.

        A batch run is hours long and unattended; a single network blip or
        5xx should not end it. Client errors (4xx) are returned as-is —
        those are our fault and retrying won't help.
        """
        delay = 2.0
        for attempt in range(1, attempts + 1):
            try:
                response = self._session.post(
                    CARTESIA_TTS_BYTES_URL, json=payload, timeout=120
                )
            except requests.RequestException as exc:
                if attempt == attempts:
                    raise
                print(f"    network error ({type(exc).__name__}); "
                      f"retry {attempt}/{attempts - 1} in {delay:.0f}s")
            else:
                if response.status_code < 500 or attempt == attempts:
                    return response
                print(f"    Cartesia {response.status_code}; "
                      f"retry {attempt}/{attempts - 1} in {delay:.0f}s")
            time.sleep(delay)
            delay *= 2
        raise RuntimeError("unreachable")

    def synthesize(
        self,
        text: str,
        voice_id: str,
        model_id: str,
        speed: float,
        emotion: str | None = None,
        output_format: dict[str, Any] | None = None,
    ) -> bytes:
        generation_config: dict[str, Any] = {}
        # Omit speed entirely at 1.0: a speed of exactly 1.0 should mean
        # "whatever the model does natively", not "apply a 1.0 adjustment".
        if abs(speed - 1.0) > 1e-9:
            generation_config["speed"] = speed
        if emotion:
            generation_config["emotion"] = emotion
        payload = {
            "model_id": model_id,
            "transcript": text,
            "voice": {"mode": "id", "id": voice_id},
            "language": "en",
            "output_format": output_format or mp3_format(DEFAULT_MP3_BIT_RATE),
            "generation_config": generation_config,
        }
        response = self._post_with_retry(payload)
        if response.status_code == 400 and emotion:
            # An emotion label Cartesia doesn't accept shouldn't sink a whole
            # batch — drop it and keep the run going, loudly.
            print(
                f"  WARNING: Cartesia rejected emotion '{emotion}' "
                f"(400); regenerating this clip without it. Fix "
                f"tone_emotions in {VOICE_CONFIG_PATH.name}."
            )
            generation_config.pop("emotion", None)
            payload["generation_config"] = generation_config
            response = self._post_with_retry(payload)
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


def narration_units_for_lang(
    story: dict[str, Any], lang: str
) -> list[tuple[str, str]]:
    """The units to voice, in `lang`.

    English is the story's own prose. Any other language reads from
    `story["narration"][lang]` — a narration SCRIPT, not display text: the
    page still shows English, so the script must stay paragraph-for-paragraph
    aligned with it or clip N stops matching paragraph N on screen.

    Coverage must be complete. A half-translated story would switch language
    mid-read, which is worse than not offering the language at all.
    """
    english = narration_units(story)
    if lang == "en":
        return english
    script = (story.get("narration") or {}).get(lang)
    if not script:
        raise SystemExit(
            f"{story['id']} has no narration script for '{lang}' — add "
            f"story['narration']['{lang}'] before voicing it"
        )
    by_unit: dict[str, str] = dict(script.get("segments") or {})
    by_unit.update(script.get("choice_points") or {})
    out: list[tuple[str, str]] = []
    for unit_id, english_prose in english:
        translated = by_unit.get(unit_id)
        if not translated:
            raise SystemExit(
                f"{story['id']} narration['{lang}'] is missing unit "
                f"'{unit_id}' — a partial script would switch language "
                f"mid-story"
            )
        want = len(story_audio_chunks.paragraph_chunks(english_prose))
        got = len(story_audio_chunks.paragraph_chunks(translated))
        if want != got:
            raise SystemExit(
                f"{story['id']} narration['{lang}'] unit '{unit_id}' has "
                f"{got} paragraph(s) but the English has {want}. The player "
                f"plays clip N against paragraph N, so they must match — keep "
                f"the blank lines exactly as they are in the English."
            )
        out.append((unit_id, translated))
    return out


def generate_story(
    story: dict[str, Any],
    client: CartesiaBatchClient,
    voice_config: dict[str, Any],
    site_audio_dir: Path,
    force: bool,
    previous_manifest: dict[str, Any],
    lang: str = "en",
) -> tuple[dict[str, Any], int, int]:
    """Generate all chunks for one story. Returns (manifest_entry,
    chars_sent, files_written)."""
    voice = voice_for_story(story, voice_config, lang)
    voice_id = voice["voice_id"]
    speed = voice["speed"]
    emotion = voice["emotion"]
    sentence_pause_ms = voice["sentence_pause_ms"]
    model_id = voice_config["model_id"]
    mp3_bit_rate = int(voice_config.get("mp3_bit_rate", DEFAULT_MP3_BIT_RATE))
    current_settings = {
        "voice_id": voice_id,
        "model_id": model_id,
        "speed": speed,
        "emotion": emotion,
        "sentence_pause_ms": sentence_pause_ms,
        "mp3_bit_rate": mp3_bit_rate,
    }
    # Only meaningful for a story that HAS clips already: with no previous
    # entry every setting trivially "differs", which would tell you to
    # --force a story that is simply being voiced for the first time.
    previous_entry = previous_manifest.get(story["id"])
    if previous_entry and lang != "en":
        previous_entry = (previous_entry.get("languages") or {}).get(lang)
    drift = settings_drift(previous_entry, current_settings) if previous_entry else []
    if drift and not force:
        print(
            f"  NOTE: {', '.join(drift)} changed since these clips were made, "
            f"but existing mp3s are kept. Re-run with --force to hear the "
            f"new settings."
        )
    slots = story.get("slots") or {}
    if lang != "en":
        # Slot DEFAULTS are English ("the green cat's-eye marble"). Spoken
        # inside a translated sentence that lands as an English clause in the
        # middle of the story, so a script may localise them.
        localised = ((story.get("narration") or {}).get(lang) or {}).get("slots") or {}
        slots = {
            name: ({**slot, "default": localised[name]} if name in localised else slot)
            for name, slot in slots.items()
        }
        missing = [n for n in slots if n not in localised]
        if missing:
            print(
                f"  NOTE: slot(s) {missing} have no {lang} default — their "
                f"English wording will be spoken inside the translated prose"
            )

    story_dir = site_audio_dir / story["id"]
    if lang != "en":
        story_dir = story_dir / lang
    story_dir.mkdir(parents=True, exist_ok=True)

    manifest_segments: dict[str, list[dict[str, Any]]] = {}
    chars_sent = 0
    files_written = 0
    for unit_id, prose in narration_units_for_lang(story, lang):
        chunk_entries: list[dict[str, Any]] = []
        for index, chunk_text in enumerate(story_audio_chunks.paragraph_chunks(prose)):
            slot_tokens = story_audio_chunks.declared_slot_tokens(chunk_text, slots)
            spoken_text = story_audio_chunks.substitute_slot_values(
                chunk_text, slots, {}
            )
            transcript = story_audio_chunks.to_transcript(
                spoken_text, sentence_pause_ms
            )
            file_name = f"{unit_id}_{index:02d}.mp3"
            file_path = story_dir / file_name
            if force or not file_path.is_file():
                started = time.monotonic()
                file_path.write_bytes(
                    client.synthesize(
                        transcript, voice_id, model_id, speed, emotion,
                        mp3_format(mp3_bit_rate),
                    )
                )
                chars_sent += len(transcript)
                files_written += 1
                print(
                    f"  {story['id']}/{lang if lang != 'en' else ''}"
                    f"{'/' if lang != 'en' else ''}{file_name}: "
                    f"{len(transcript)} chars in {time.monotonic() - started:.1f}s"
                )
            chunk_entries.append(
                {
                    "i": index,
                    "file": file_name,
                    "has_slot": bool(slot_tokens),
                    "chars": len(transcript),
                }
            )
        manifest_segments[unit_id] = chunk_entries
    manifest_entry = dict(current_settings)
    manifest_entry["segments"] = manifest_segments
    return manifest_entry, chars_sent, files_written


PAUSE_TEST_MS = (0, 150, 250, 350, 500)


def run_pause_test(story_substring: str, voice_config: dict[str, Any]) -> int:
    """Same passage, same voice settings, one pause length per file.

    Sentence pauses are the one setting you can't judge from a single clip:
    too short and the read runs together, too long and it drags. This holds
    everything else at the shipped config and varies only the pause, so the
    choice is a straight listen-and-pick.
    """
    client = CartesiaBatchClient()
    stories = [s for s in bse.load_stories() if story_substring in s["id"]]
    if not stories:
        raise SystemExit(f"no story id contains {story_substring!r}")
    story = stories[0]
    settings = voice_for_story(story, voice_config)
    bit_rate = int(voice_config.get("mp3_bit_rate", DEFAULT_MP3_BIT_RATE))

    opening = next(
        seg for seg in story["segments"] if seg["id"] == story["start_segment"]
    )
    # Several paragraphs, so there are plenty of sentence boundaries to judge.
    paragraphs = story_audio_chunks.paragraph_chunks(opening["text"])[:3]
    plain = story_audio_chunks.substitute_slot_values(
        " ".join(paragraphs), story.get("slots") or {}, {}
    )

    DIAGNOSE_DIR.mkdir(parents=True, exist_ok=True)
    print(
        f"pause test on {story['id']}\n"
        f"  holding voice={settings['voice_id']}, speed={settings['speed']}, "
        f"emotion={settings['emotion'] or 'none'}, mp3={bit_rate // 1000}k\n"
    )
    for pause_ms in PAUSE_TEST_MS:
        transcript = story_audio_chunks.to_transcript(plain, pause_ms)
        out_path = DIAGNOSE_DIR / f"pause_{pause_ms:03d}ms.mp3"
        out_path.write_bytes(
            client.synthesize(
                transcript,
                settings["voice_id"],
                voice_config["model_id"],
                settings["speed"],
                settings["emotion"],
                mp3_format(bit_rate),
            )
        )
        print(f"  wrote {out_path.name} ({transcript.count('<break')} breaks)")
    print(
        f"\nListen in {DIAGNOSE_DIR} and put the winner in "
        f"{VOICE_CONFIG_PATH.name} as sentence_pause_ms, then regenerate "
        f"with --force. (pause_000ms is the no-breaks reference.)"
    )
    return 0


def run_diagnose(story_substring: str, voice_config: dict[str, Any]) -> int:
    """Render one passage under a matrix of settings, one variable at a time.

    When a voice sounds wrong (nasal, watery, clicky) after several knobs
    were turned at once, guessing is expensive. This renders the SAME text
    with each knob isolated, into numbered files whose names say what they
    are — play them in order and the culprit announces itself.

    01 is the reference: no speed adjustment, no emotion, no break tags,
    lossless WAV. If 01 already sounds wrong, it's the voice or the model,
    not us. Whichever numbered file first sounds wrong names the cause.
    """
    client = CartesiaBatchClient()
    stories = [s for s in bse.load_stories() if story_substring in s["id"]]
    if not stories:
        raise SystemExit(f"no story id contains {story_substring!r}")
    story = stories[0]
    settings = voice_for_story(story, voice_config)
    model_id = voice_config["model_id"]
    voice_id = settings["voice_id"]
    bit_rate = int(voice_config.get("mp3_bit_rate", DEFAULT_MP3_BIT_RATE))
    # Probe values, NOT the live config: once a knob has been turned off in
    # audio_voices.json its trial would otherwise collapse into the
    # reference and the matrix would silently stop testing anything.
    speed = settings["speed"] if abs(settings["speed"] - 1.0) > 1e-9 else 0.94
    tone = (story.get("tone") or {}).get("dominant")
    emotion = (
        settings["emotion"]
        or (voice_config.get("tone_emotions") or {}).get(tone)
        or "content"
    )
    pause_ms = settings["sentence_pause_ms"] or 250

    opening = next(
        seg for seg in story["segments"] if seg["id"] == story["start_segment"]
    )
    paragraphs = story_audio_chunks.paragraph_chunks(opening["text"])[:2]
    plain = story_audio_chunks.substitute_slot_values(
        " ".join(paragraphs), story.get("slots") or {}, {}
    )
    broken = story_audio_chunks.to_transcript(plain, pause_ms)

    # (label, transcript, speed, emotion, output_format, extension)
    trials: list[tuple[str, str, float, str | None, dict[str, Any], str]] = [
        ("01_reference_wav_nospeed_noemotion_nobreaks",
         plain, 1.0, None, WAV_OUTPUT_FORMAT, "wav"),
        (f"02_mp3_{bit_rate // 1000}k_nospeed_noemotion_nobreaks",
         plain, 1.0, None, mp3_format(bit_rate), "mp3"),
        ("03_mp3_96k_nospeed_noemotion_nobreaks",
         plain, 1.0, None, mp3_format(96000), "mp3"),
        ("03b_mp3_192k_nospeed_noemotion_nobreaks",
         plain, 1.0, None, mp3_format(192000), "mp3"),
        (f"04_mp3_{bit_rate // 1000}k_speed{speed}_noemotion_nobreaks",
         plain, speed, None, mp3_format(bit_rate), "mp3"),
        (f"05_mp3_{bit_rate // 1000}k_nospeed_emotion-{emotion or 'none'}_nobreaks",
         plain, 1.0, emotion, mp3_format(bit_rate), "mp3"),
        (f"06_mp3_{bit_rate // 1000}k_nospeed_noemotion_breaks{pause_ms}ms",
         broken, 1.0, None, mp3_format(bit_rate), "mp3"),
        ("07_everything_on_current_settings",
         broken, speed, emotion, mp3_format(bit_rate), "mp3"),
    ]

    DIAGNOSE_DIR.mkdir(parents=True, exist_ok=True)
    print(
        f"diagnosing {story['id']}\n"
        f"  current settings: speed={speed}, emotion={emotion or 'none'}, "
        f"pause={pause_ms}ms, mp3={bit_rate // 1000}k\n"
    )
    for label, transcript, trial_speed, trial_emotion, fmt, ext in trials:
        out_path = DIAGNOSE_DIR / f"{label}.{ext}"
        out_path.write_bytes(
            client.synthesize(
                transcript, voice_id, model_id, trial_speed, trial_emotion, fmt
            )
        )
        print(f"  wrote {out_path.name}")
    print(
        f"\nPlay them in order from {DIAGNOSE_DIR}.\n"
        "  01 bad            -> the voice/model itself, not our settings\n"
        "  02 bad, 01 fine   -> mp3 encoding; raise mp3_bit_rate\n"
        "  04 bad            -> the speed adjustment; set speed to 1.0\n"
        "  05 bad            -> the emotion; drop it from tone_emotions\n"
        "  06 bad            -> break tags; lower/zero sentence_pause_ms\n"
        "then set the winning values in audio_voices.json and regenerate "
        "with --force."
    )
    return 0


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
                client.synthesize(
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


def load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.is_file():
        return {}
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return json.load(f)


def merge_manifest(new_entries: dict[str, Any]) -> None:
    manifest = load_manifest()
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
    parser.add_argument("--diagnose", metavar="ID_SUBSTRING",
                        help="render one passage under a matrix of settings to "
                             "find what is making a voice sound wrong")
    parser.add_argument("--pause-test", metavar="ID_SUBSTRING",
                        help="render one passage at several sentence-pause "
                             "lengths so you can pick one by ear")
    parser.add_argument("--lang", default="en", metavar="CODE",
                        help="narration language (default en). Anything else "
                             "reads story['narration'][CODE] and writes clips "
                             "to <story_id>/<CODE>/, leaving English untouched")
    parser.add_argument("--force", action="store_true",
                        help="regenerate mp3s that already exist")
    parser.add_argument("--upload", action="store_true",
                        help="after generating, rsync each story's clips to "
                             "the serving bucket (gcloud auth required)")
    parser.add_argument("--site-audio-dir", type=Path, default=DEFAULT_SITE_AUDIO_DIR,
                        help=f"where mp3s land locally (default: {DEFAULT_SITE_AUDIO_DIR})")
    args = parser.parse_args()

    voice_config = load_voice_config()
    if args.pause_test:
        return run_pause_test(args.pause_test, voice_config)
    if args.diagnose:
        return run_diagnose(args.diagnose, voice_config)
    if args.audition:
        return run_audition(args.audition, voice_config)
    if not args.stories and not args.all:
        parser.error(
            "pick stories with --stories, or use --all / --audition / --diagnose"
        )

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
    previous_manifest = load_manifest()
    new_manifest_entries: dict[str, Any] = {}
    total_chars = 0
    total_files = 0
    for story in sorted(stories, key=lambda s: s["id"]):
        settings = voice_for_story(story, voice_config, args.lang)
        print(
            f"{story['id']} [{args.lang}] ({story['teller']} / "
            f"{(story.get('tone') or {}).get('dominant')} → "
            f"emotion={settings['emotion'] or 'none'}, "
            f"speed={settings['speed']}, "
            f"pause={settings['sentence_pause_ms']}ms):"
        )
        manifest_entry, chars_sent, files_written = generate_story(
            story, client, voice_config, args.site_audio_dir, args.force,
            previous_manifest, args.lang,
        )
        if args.lang != "en":
            # Keep English at the top level — 100+ existing entries have that
            # shape and build_pilot_site reads it — and hang other languages
            # off it, so one story is still one manifest entry.
            existing = dict(previous_manifest.get(story["id"]) or {})
            languages = dict(existing.get("languages") or {})
            languages[args.lang] = manifest_entry
            existing["languages"] = languages
            manifest_entry = existing
        new_manifest_entries[story["id"]] = manifest_entry
        # Persist per story: an 80-story run that dies at story 70 must not
        # throw away the manifest for the 69 that succeeded.
        merge_manifest({story["id"]: manifest_entry})
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
