"""Pace test: one passage, a few (speed, pause) settings, pick by ear.

Run from the repo root (never `python -m`, never PYTHONPATH=.):

    python scripts/pace_test.py 1185fc            # The Great Orange Sunset Machine
    python scripts/pace_test.py 1185fc --trial 0.94:250 --trial 0.92:300:25:150

Why this exists: `--pause-test` varies only the pause and `--diagnose` hunts
artifacts one knob at a time. This answers the 5-6 question directly —
"slower words, shorter sentence gaps, and a shorter gap after a short
sentence" — by rendering the SAME passage under each candidate, side by side.

Faithful to production: every paragraph is its own Cartesia request, exactly
as generate_story_audio.py does it (one clip = one paragraph; never one
request with twenty break tags, which Cartesia warns can hallucinate). The
clips are then stitched with a silence the length of the player's paragraph
gap for that band (NARRATION_TUNING.chunkGapMs × bandScale in
pilot/js/stories.js) so each trial is one file that sounds like playback.
Stitching needs ffmpeg; without it you get the per-paragraph clips and a
note, which is still a fair listen — just tap through them.

Output: story_definitions/preview/audio_diagnose/pace_<hash>/
    NN_<label>.mp3            stitched trial (ffmpeg)
    NN_<label>/p00.mp3 …      the per-paragraph clips, as production makes them
    about.txt                 settings + exact transcripts
Cost is printed. Four trials on ~700 chars is ~3k chars.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import build_story_explorer as bse
import generate_story_audio as gsa
import story_audio_chunks

# Player-side paragraph gap, mirrored from pilot/js/stories.js
# NARRATION_TUNING (chunkGapMs 550 × bandScale). Used only to stitch the test
# file; nothing here changes the player.
PLAYER_CHUNK_GAP_MS = 550
PLAYER_BAND_SCALE = {"3-4": 1.8, "5-6": 1.5, "7-8": 1.2, "9-10": 1.0, "11-12": 0.9}

# (label, speed, sentence_pause_ms, short_sentence_chars, short_sentence_pause_ms)
DEFAULT_TRIALS = [
    ("reference_speed1.00_pause400", 1.0, 400, 0, None),
    ("speed0.95_pause300", 0.95, 300, 0, None),
    ("speed0.92_pause300", 0.92, 300, 0, None),
    ("speed0.92_pause300_short25to200", 0.92, 300, 25, 200),
]


def parse_trial(spec: str) -> tuple[str, float, int, int, int | None]:
    """--trial SPEED:PAUSE[:SHORT_CHARS:SHORT_PAUSE], e.g. 0.94:250 or 0.92:300:25:150"""
    parts = spec.split(":")
    if len(parts) not in (2, 4):
        raise SystemExit(
            f"bad --trial {spec!r}: want SPEED:PAUSE or SPEED:PAUSE:SHORT_CHARS:SHORT_PAUSE"
        )
    speed, pause = float(parts[0]), int(parts[1])
    short_chars, short_pause = (
        (int(parts[2]), int(parts[3])) if len(parts) == 4 else (0, None)
    )
    label = f"speed{speed:.2f}_pause{pause}"
    if short_chars:
        label += f"_short{short_chars}to{short_pause}"
    return (label, speed, pause, short_chars, short_pause)


def stitch(clips: list[Path], gap_ms: int, out_path: Path, bit_rate: int) -> bool:
    """Concatenate clips with gap_ms of silence after each, via ffmpeg.
    Returns False (and writes nothing) when ffmpeg is not installed."""
    if not shutil.which("ffmpeg"):
        return False
    command = ["ffmpeg", "-y", "-loglevel", "error"]
    for clip in clips:
        command += ["-i", str(clip)]
    pads = "".join(
        f"[{i}:a]apad=pad_dur={gap_ms / 1000:.3f}[a{i}];" for i in range(len(clips))
    )
    chain = "".join(f"[a{i}]" for i in range(len(clips)))
    command += [
        "-filter_complex", f"{pads}{chain}concat=n={len(clips)}:v=0:a=1[out]",
        "-map", "[out]", "-codec:a", "libmp3lame", "-b:a", f"{bit_rate // 1000}k",
        str(out_path),
    ]
    subprocess.run(command, check=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("story", metavar="ID_SUBSTRING",
                        help="story id substring (use the 6-hex hash)")
    parser.add_argument("--paragraphs", type=int, default=8,
                        help="paragraphs of the opening segment to use (default 8)")
    parser.add_argument("--trial", action="append", default=[],
                        metavar="SPEED:PAUSE[:CHARS:PAUSE]",
                        help="replace the default matrix; repeatable")
    parser.add_argument("--voice", metavar="VOICE_ID",
                        help="override the voice (default: what the story ships with)")
    args = parser.parse_args()

    voice_config = gsa.load_voice_config()
    stories = [s for s in bse.load_stories() if args.story in s["id"]]
    if not stories:
        raise SystemExit(f"no story id contains {args.story!r}")
    if len(stories) > 1:
        raise SystemExit("ambiguous: " + ", ".join(s["id"] for s in stories))
    story = stories[0]
    settings = gsa.voice_for_story(story, voice_config)
    voice_id = args.voice or settings["voice_id"]
    model_id = voice_config["model_id"]
    bit_rate = int(voice_config.get("mp3_bit_rate", gsa.DEFAULT_MP3_BIT_RATE))
    band = story.get("age_band", "")
    gap_ms = round(PLAYER_CHUNK_GAP_MS * PLAYER_BAND_SCALE.get(band, 1.0))

    opening = next(
        seg for seg in story["segments"] if seg["id"] == story["start_segment"]
    )
    paragraphs = [
        story_audio_chunks.substitute_slot_values(p, story.get("slots") or {}, {})
        for p in story_audio_chunks.paragraph_chunks(opening["text"])[: args.paragraphs]
    ]

    trials = [parse_trial(t) for t in args.trial] or DEFAULT_TRIALS
    out_dir = gsa.DIAGNOSE_DIR / f"pace_{story['id'].rsplit('.', 1)[-1]}"
    out_dir.mkdir(parents=True, exist_ok=True)
    have_ffmpeg = bool(shutil.which("ffmpeg"))

    print(f"pace test on {story['id']} (band {band}, teller {story['teller']})")
    print(f"  voice {voice_id}, {model_id}, mp3 {bit_rate // 1000}k, "
          f"emotion {settings['emotion'] or 'none'}")
    print(f"  passage: {len(paragraphs)} paragraphs, "
          f"{sum(len(p) for p in paragraphs)} chars; paragraph gap {gap_ms}ms"
          + ("" if have_ffmpeg else "  (no ffmpeg: per-paragraph clips only)") + "\n")

    client = gsa.CartesiaBatchClient()
    notes = [
        f"story: {story['id']}", f"band: {band}", f"voice_id: {voice_id}",
        f"model_id: {model_id}", f"mp3_bit_rate: {bit_rate}",
        f"paragraph gap between clips (player chunkGapMs x bandScale): {gap_ms}ms",
        "one Cartesia request per paragraph, as production does it", "",
    ]
    chars_sent = 0
    for number, (label, speed, pause, short_chars, short_pause) in enumerate(trials, 1):
        clip_dir = out_dir / f"{number:02d}_{label}"
        clip_dir.mkdir(exist_ok=True)
        clips: list[Path] = []
        total_seconds = 0.0
        breaks = 0
        notes += [f"{number:02d}_{label}",
                  f"  speed={speed}  sentence_pause_ms={pause}  "
                  f"short_sentence_chars={short_chars}  short_sentence_pause_ms={short_pause}"]
        for index, paragraph in enumerate(paragraphs):
            transcript = story_audio_chunks.to_transcript(
                paragraph, pause, short_chars, short_pause
            )
            audio = client.synthesize(
                transcript, voice_id, model_id, speed, settings["emotion"],
                gsa.mp3_format(bit_rate),
            )
            audio, _ = gsa._without_silent_tail(
                audio, transcript, client, voice_id, model_id, speed,
                settings["emotion"], bit_rate, f"{label}/p{index:02d}",
            )
            clip = clip_dir / f"p{index:02d}.mp3"
            clip.write_bytes(audio)
            clips.append(clip)
            chars_sent += len(transcript)
            total_seconds += len(audio) * 8 / bit_rate
            breaks += transcript.count("<break")
            notes.append(f"  p{index:02d}: {transcript}")
        stitched = out_dir / f"{number:02d}_{label}.mp3"
        joined = stitch(clips, gap_ms, stitched, bit_rate)
        speech = f"{total_seconds:.0f}s speech + {gap_ms * (len(clips) - 1) / 1000:.1f}s gaps"
        print(f"  {stitched.name if joined else clip_dir.name + '/'}: "
              f"{speech}, {breaks} sentence breaks")
        notes += [f"  {speech}, {breaks} break tags", ""]
    (out_dir / "about.txt").write_text("\n".join(notes) + "\n", encoding="utf-8")

    print(f"\ndone: {chars_sent} chars sent to Cartesia. "
          f"Listen in {out_dir.relative_to(gsa.REPO_ROOT)}")
    if not have_ffmpeg:
        print("  ffmpeg not found, so no stitched files: play each trial's "
              "p00…p07 in order (brew install ffmpeg to get one file per trial).")
    print("Winner -> audio_voices.json age_bands.<band> (speed, sentence_pause_ms, "
          "short_sentence_chars, short_sentence_pause_ms), then re-cut with "
          "--band <band> --force (or --stories … --force for a subset).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
