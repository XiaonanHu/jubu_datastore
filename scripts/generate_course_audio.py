#!/usr/bin/env python3
"""Narrate a COURSE story with word-level timestamps, for the read-along cursor.

Run from the jubu_datastore repo root as a script (never `python -m`,
never PYTHONPATH=.):

    # 1. prove the endpoint and see the raw event shape (one short phrase, ~1s)
    python scripts/generate_course_audio.py --probe

    # 2. narrate the story
    python scripts/generate_course_audio.py \
        --story story_definitions/stories/courses/frustration__age5to6__d1__course__c41a7b.json

    # 3. re-do one segment after a text edit
    python scripts/generate_course_audio.py --story <path> --only s3 --force

WHY A SEPARATE SCRIPT. generate_story_audio.py drives 142 published clips and
uses /tts/bytes, which returns audio and nothing else. This uses /tts/sse with
add_timestamps, which returns audio AND a word-by-word time array. Keeping them
apart means the pilot pipeline cannot break while we experiment here.

UNIT OF AUDIO is one SEGMENT, not one paragraph. Course segments are short and
a single clip gives unbroken word timings across the whole segment. The trade:
slot values (the friend's name) are baked in, so changing the name in course
settings needs a --force regeneration. Fine for a class-set name; if that
becomes annoying, switch to per-sentence clips and re-voice only the sentences
that carry a slot.

Writes:
  story_definitions/preview/course_audio/<story_id>/<segment>.wav (or .mp3 with ffmpeg)
  ... and an `audio` block onto the story JSON:
      "audio": {"segments": {"s1": {"file": "s1.mp3", "duration": 8.4,
                                    "words": [{"w":"Pip","start":0.02,"end":0.21}, ...]}}}
LISTEN before this reaches a child. Same gate as the pilot.
"""
from __future__ import annotations
import argparse, base64, json, os, re, sys, time
from pathlib import Path

import shutil, subprocess, wave

import requests

CARTESIA_SSE_URL = "https://api.cartesia.ai/tts/sse"
CARTESIA_API_VERSION = "2026-03-01"        # must match generate_story_audio.py

# /tts/sse returns RAW PCM only — it rejects an mp3 container with
# "only 'raw' container is supported for this endpoint". So we ask for
# signed 16-bit PCM and wrap it in a WAV header ourselves (stdlib `wave`,
# no dependency). If ffmpeg is on PATH we also emit an mp3, which is ~10x
# smaller; the player takes either.
SAMPLE_RATE = 44100
RAW_PCM = {"container": "raw", "encoding": "pcm_s16le", "sample_rate": SAMPLE_RATE}

# Sentence pauses are BAKED IN as SSML, exactly like the pilot pipeline, and
# resolved age_bands > tellers > top level from audio_voices.json. Without
# them a K story reads at ~190-230 wpm, which is far too fast for a child to
# track a moving cursor (adult read-aloud to a 5-year-old is 120-150 wpm).
# Changing the pause needs a --force regeneration; it is inside the audio.
FALLBACK_PAUSE_MS = {"3-4": 500, "5-6": 400, "7-8": 300, "9-10": 250, "11-12": 250}
SENTENCE_END = ".!?"


# --------------------------------------------------------------------- key
def resolve_api_key() -> str:
    """Same convention as generate_story_audio.py: env first, then the
    sibling jubu_backend .env.local / .env. Never hardcode the key."""
    try:                                              # reuse theirs if importable
        sys.path.insert(0, str(Path(__file__).parent))
        from generate_story_audio import resolve_cartesia_api_key  # type: ignore
        return resolve_cartesia_api_key()
    except Exception:
        pass
    if os.environ.get("CARTESIA_API_KEY"):
        return os.environ["CARTESIA_API_KEY"]
    for rel in ("../jubu_backend/.env.local", "../jubu_backend/.env"):
        p = Path(__file__).resolve().parents[1] / rel
        if p.exists():
            for line in p.read_text().splitlines():
                if line.strip().startswith("CARTESIA_API_KEY="):
                    return line.split("=", 1)[1].strip().strip("'\"")
    raise SystemExit("CARTESIA_API_KEY not found in env or jubu_backend/.env*")


# --------------------------------------------------------------------- call
def write_audio(pcm: bytes, dest_wav: Path) -> Path:
    """Wrap raw PCM in WAV; also make an mp3 if ffmpeg is available."""
    with wave.open(str(dest_wav), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    if shutil.which("ffmpeg"):
        mp3 = dest_wav.with_suffix(".mp3")
        r = subprocess.run(["ffmpeg", "-y", "-i", str(dest_wav), "-b:a", "128k", str(mp3)],
                           capture_output=True)
        if r.returncode == 0 and mp3.exists():
            dest_wav.unlink()
            return mp3
    return dest_wav


def add_breaks(text: str, pause_ms: int) -> str:
    """Insert <break> after each sentence. Cartesia strips the tags from the
    timestamp stream, so word timings still line up with the visible text."""
    if pause_ms <= 0:
        return text
    out, buf = [], ""
    for ch in text:
        buf += ch
        if ch in SENTENCE_END:
            out.append(buf); buf = ""
    if buf.strip():
        out.append(buf)
    tag = f'<break time="{pause_ms}ms"/>'
    return tag.join(s if s.endswith(" ") else s + " " for s in out).strip()


def synthesize(text: str, voice_id: str, model_id: str, speed: float,
               key: str, verbose: bool = False):
    """POST to /tts/sse and collect raw PCM + word timestamps.

    Returns (pcm_bytes, [{"w":..,"start":..,"end":..}], raw_event_types).
    """
    gen: dict = {}
    if abs(speed - 1.0) > 1e-9:
        gen["speed"] = speed
    payload = {
        "model_id": model_id,
        "transcript": text,
        "voice": {"mode": "id", "id": voice_id},
        "language": "en",
        "output_format": RAW_PCM,
        "generation_config": gen,
        "add_timestamps": True,          # <- the whole point
    }
    headers = {"Authorization": f"Bearer {key}",
               "Cartesia-Version": CARTESIA_API_VERSION,
               "Accept": "text/event-stream"}

    audio = bytearray()
    words: list[dict] = []
    seen_types: list[str] = []

    with requests.post(CARTESIA_SSE_URL, json=payload, headers=headers,
                       stream=True, timeout=180) as r:
        if r.status_code >= 400:
            raise RuntimeError(f"Cartesia {r.status_code}: {r.text[:400]}")
        for raw in r.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data:"):
                continue
            body = raw[5:].strip()
            if body in ("", "[DONE]"):
                continue
            try:
                ev = json.loads(body)
            except json.JSONDecodeError:
                continue
            t = ev.get("type", "?")
            if t not in seen_types:
                seen_types.append(t)
                if verbose:
                    keys = sorted(ev.keys())
                    print(f"      event '{t}' keys={keys}")
            if ev.get("data"):                       # audio chunk (base64)
                audio.extend(base64.b64decode(ev["data"]))
            # word timings arrive either nested or flat depending on version
            wt = ev.get("word_timestamps") or (
                ev if {"words", "start", "end"} <= set(ev) else None)
            if wt and wt.get("words"):
                for w, s, e in zip(wt["words"], wt["start"], wt["end"]):
                    words.append({"w": w, "start": round(float(s), 3),
                                  "end": round(float(e), 3)})
    return bytes(audio), words, seen_types


# -------------------------------------------------------------------- probe
def probe(key: str, voice_id: str, model_id: str) -> int:
    text = "Pip looks down at his hands. They are tight."
    print(f"probing {CARTESIA_SSE_URL}\n  voice={voice_id} model={model_id}\n  text={text!r}\n")
    try:
        audio, words, types = synthesize(text, voice_id, model_id, 1.0, key, verbose=True)
    except Exception as e:
        print(f"  FAILED — {type(e).__name__}: {e}")
        print("\n  If this is a 4xx about 'add_timestamps', the field name or the")
        print("  Cartesia-Version pin differs. Check the current SSE docs and")
        print("  adjust CARTESIA_API_VERSION / the payload key at the top of this file.")
        return 1
    print(f"\n  event types seen: {types}")
    print(f"  raw PCM bytes: {len(audio)}  (~{len(audio)/2/SAMPLE_RATE:.2f}s)")
    print(f"  words returned: {len(words)}")
    for w in words[:8]:
        print(f"    {w['w']:>8}  {w['start']:.3f} -> {w['end']:.3f}")
    if not words:
        print("\n  Audio came back but NO timings. add_timestamps was accepted and")
        print("  ignored, or the event shape changed. Re-run with the printed event")
        print("  keys above and adjust the wt = ... line.")
        return 1
    out = write_audio(audio, Path("probe.wav"))
    print(f"\n  wrote {out.name} — play it, then run the real thing.")
    return 0


# --------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--story")
    ap.add_argument("--only", nargs="*", help="segment ids; default all")
    ap.add_argument("--voice", default=None, help="override voice id")
    ap.add_argument("--model", default="sonic-3")
    ap.add_argument("--speed", type=float, default=None)
    ap.add_argument("--pause-ms", type=int, default=None,
                    help="sentence pause baked into the clip; default from audio_voices.json")
    ap.add_argument("--wpm-warn", type=float, default=165.0,
                    help="warn above this words-per-minute; K read-along wants 120-150")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--probe", action="store_true")
    a = ap.parse_args()

    key = resolve_api_key()
    repo = Path(__file__).resolve().parents[1]
    voices = {}
    vp = repo / "story_definitions" / "audio_voices.json"
    if vp.exists():
        voices = json.loads(vp.read_text())

    def pick(band: str, teller: str):
        """voice, speed and sentence pause: age_bands > tellers > top level,
        the same order the pilot pipeline resolves in."""
        v = voices.get("age_bands", {}).get(band, {})
        t = voices.get("tellers", {}).get(teller, {})
        vid = a.voice or v.get("voice_id") or t.get("voice_id") or voices.get("voice_id")
        spd = a.speed if a.speed is not None else (
            v.get("speed") or t.get("speed") or voices.get("speed") or 1.0)
        pause = a.pause_ms if a.pause_ms is not None else (
            v.get("sentence_pause_ms") or t.get("sentence_pause_ms")
            or voices.get("sentence_pause_ms") or FALLBACK_PAUSE_MS.get(band, 300))
        return vid, float(spd), int(pause)

    if a.probe:
        vid, spd, _ = pick("5-6", "named_hero")
        if not vid:
            return print("no voice id — pass --voice <id>") or 1
        return probe(key, vid, a.model)

    if not a.story:
        return print("need --story (or --probe)") or 1

    sp = Path(a.story).resolve()
    story = json.loads(sp.read_text())
    root = next((q for q in sp.parents if (q / "story_definitions").is_dir()), sp.parent)
    base = root / "story_definitions"
    out = base / "preview" / "course_audio" / story["id"]
    out.mkdir(parents=True, exist_ok=True)

    vid, spd, pause = pick(story["age_band"], story.get("teller", ""))
    if not vid:
        return print("no voice id resolved — pass --voice <id>") or 1

    slots = story.get("slots", {})
    fill = lambda t: re.sub(r"\{(\w+)\}", lambda m: slots[m.group(1)]["default"], t)

    print(f"{story['title']}  ->  {out}")
    print(f"voice={vid} model={a.model} speed={spd} sentence_pause={pause}ms\n")

    manifest = story.get("audio", {}).get("segments", {})
    targets = [s for s in story["segments"] if not a.only or s["id"] in a.only]
    chars = 0
    for seg in targets:
        dest = next((out / f"{seg['id']}{e}" for e in (".mp3", ".wav")
                     if (out / f"{seg['id']}{e}").exists()), out / f"{seg['id']}.wav")
        if dest.exists() and not a.force:
            print(f"  {seg['id']}: exists, skipping (--force to redo)")
            continue
        text = fill(seg["text"])
        t0 = time.monotonic()
        try:
            audio, words, _ = synthesize(add_breaks(text, pause), vid, a.model, spd, key)
        except Exception as e:
            print(f"  {seg['id']}: FAILED — {type(e).__name__}: {e}")
            continue
        if not audio:
            print(f"  {seg['id']}: no audio returned"); continue
        written = write_audio(audio, out / f"{seg['id']}.wav")
        dur = words[-1]["end"] if words else round(len(audio) / 2 / SAMPLE_RATE, 3)
        manifest[seg["id"]] = {"file": written.name, "duration": dur,
                               "words": words, "text": text}
        chars += len(text)
        wpm = len(words) / dur * 60 if dur else 0
        flag = "  <-- FAST" if wpm > a.wpm_warn else ""
        print(f"  {seg['id']}: {written.name} {written.stat().st_size//1024} KB, "
              f"{len(words)} words, {dur}s, {wpm:.0f} wpm{flag}"
              f"  ({time.monotonic()-t0:.1f}s)")

    # choice questions get clips too, so the reader can speak the question
    for cp in story.get("choice_points", []):
        cid = cp["id"]
        if a.only and cid not in a.only:
            continue
        if any((out / f"{cid}{e}").exists() for e in (".mp3", ".wav")) and not a.force:
            continue
        text = fill(cp["question"])
        try:
            audio, words, _ = synthesize(add_breaks(text, pause), vid, a.model, spd, key)
        except Exception as e:
            print(f"  {cid}: FAILED — {e}"); continue
        if audio:
            written = write_audio(audio, out / f"{cid}.wav")
            manifest[cid] = {"file": written.name,
                             "duration": words[-1]["end"] if words
                                         else round(len(audio)/2/SAMPLE_RATE, 3),
                             "words": words, "text": text}
            chars += len(text)
            print(f"  {cid}: {written.name}, {len(words)} words")

    if manifest:
        story["audio"] = {"source": "cartesia_sse_timestamps",
                          "model_id": a.model, "voice_id": vid, "speed": spd,
                          "segments": manifest}
        sp.write_text(json.dumps(story, indent=2, ensure_ascii=False))
        paced = [m for m in manifest.values() if m.get("duration") and m.get("words")]
        if paced:
            avg = sum(len(m["words"]) / m["duration"] * 60 for m in paced) / len(paced)
            print(f"\naverage pace: {avg:.0f} wpm "
                  f"({'ok for read-along' if avg <= a.wpm_warn else 'TOO FAST — raise --pause-ms or lower --speed'})")
        print(f"{len(manifest)} clip(s); {chars} characters sent.")
        print(f"Timings written onto {sp.name}.")
        print("LISTEN before this reaches a child.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
