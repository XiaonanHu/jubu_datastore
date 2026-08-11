"""One command to publish approved narration: upload, rebuild, ship, push.

Run from the repo root (never `python -m`, never PYTHONPATH=.):

    python scripts/publish_pilot_audio.py

This is the whole tail of the audio workflow, in the order that keeps the
site consistent at every moment:

  1. upload reviewed clips to gs://buju-pilot-audio (idempotent rsync)
  2. rebuild pilot_site so stories.json carries the audio stamps
  3. verify every clip stories.json references actually exists in the
     bucket — the check that prevents "Listen buttons but silence"
  4. copy stories.json + the explorer into buju_website
  5. run the website's pilot test suites
  6. commit and push jubu_datastore, then buju_website

Order matters: clips reach the bucket BEFORE the data that points at them
is deployed, so a family can never load a story whose audio isn't there
yet. Only the audio-related paths are staged, so unrelated work in
progress is never swept into these commits.

This deliberately does NOT generate audio. Generation is a separate
command because listening to the result is the quality gate:

    python scripts/generate_story_audio.py --stories <ids> [--force]
    # listen to story_definitions/preview/pilot_audio/...
    python scripts/publish_pilot_audio.py

Flags: --dry-run (show every command, change nothing), --no-push (commit
but stay local), --skip-tests, -m "commit message", --website <path>.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# Mirrors generate_story_audio.py — keep in sync if those move.
LOCAL_AUDIO_DIR = REPO_ROOT / "story_definitions" / "preview" / "pilot_audio"
MANIFEST_PATH = REPO_ROOT / "story_definitions" / "audio_manifest.json"
VOICE_CONFIG_PATH = REPO_ROOT / "story_definitions" / "audio_voices.json"
BUILT_SITE_DIR = REPO_ROOT / "story_definitions" / "preview" / "pilot_site"
DEFAULT_WEBSITE_ROOT = REPO_ROOT.parent / "buju_website"
DEFAULT_AUDIO_BUCKET = "buju-pilot-audio"

DATASTORE_COMMIT_PATHS = [
    "story_definitions/audio_manifest.json",
    "story_definitions/audio_voices.json",
    "story_definitions/preview/pilot_site",
]
WEBSITE_COMMIT_PATHS = ["pilot/data/stories.json", "pilot/explorer"]
WEBSITE_TEST_DIR = Path("tests") / "pilot"


class Failed(Exception):
    """A step failed; the message is already user-facing."""


def step(number: int, title: str) -> None:
    print(f"\n\033[1m[{number}/6] {title}\033[0m")


def run(
    command: list[str],
    cwd: Path,
    dry_run: bool,
    capture: bool = False,
    allow_failure: bool = False,
) -> str:
    printable = " ".join(command)
    if dry_run:
        print(f"    would run: {printable}   (in {cwd})")
        return ""
    print(f"    $ {printable}")
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    if result.returncode != 0 and not allow_failure:
        if capture and result.stdout:
            print(result.stdout)
        raise Failed(f"`{printable}` failed with exit code {result.returncode}")
    return result.stdout or ""


def voiced_story_ids() -> list[str]:
    if not MANIFEST_PATH.is_file():
        raise Failed(
            f"no {MANIFEST_PATH.name} yet — run generate_story_audio.py first"
        )
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return sorted(json.load(f))


def upload_clips(bucket: str, dry_run: bool) -> None:
    if not LOCAL_AUDIO_DIR.is_dir():
        raise Failed(
            f"no clips at {LOCAL_AUDIO_DIR} — run generate_story_audio.py first"
        )
    run(
        ["gcloud", "storage", "rsync", "--recursive",
         str(LOCAL_AUDIO_DIR), f"gs://{bucket}"],
        cwd=REPO_ROOT,
        dry_run=dry_run,
    )


def rebuild_site(dry_run: bool) -> int:
    output = run(
        [sys.executable, "scripts/build_pilot_site.py"],
        cwd=REPO_ROOT,
        dry_run=dry_run,
        capture=True,
    )
    if dry_run:
        return -1
    print(output.strip())
    if "WARNING: audio manifest is stale" in output:
        raise Failed(
            "the manifest is stale for at least one story (its prose changed "
            "since the clips were made) — regenerate those stories with "
            "--force before publishing"
        )
    # The build prints e.g. "wrote pilot_site: 86 stories (3 voiced), ...".
    match = re.search(r"\((\d+) voiced\)", output)
    if not match:
        raise Failed(
            "could not read the voiced-story count from build_pilot_site.py "
            "output — has its summary line changed?"
        )
    voiced = int(match.group(1))
    if voiced == 0:
        raise Failed(
            "the rebuilt stories.json has 0 voiced stories — the audio stamps "
            "are missing, so nothing would play. Check audio_manifest.json."
        )
    return voiced


def verify_bucket_coverage(bucket: str, dry_run: bool) -> None:
    """Every clip stories.json points at must already be in the bucket."""
    if dry_run:
        print(f"    would list gs://{bucket} and compare against stories.json")
        return
    built = BUILT_SITE_DIR / "data" / "stories.json"
    with open(built, encoding="utf-8") as f:
        data = json.load(f)
    wanted: set[str] = set()
    for story in data["stories"]:
        for clips in (story.get("audio") or {}).get("segments", {}).values():
            for clip in clips:
                wanted.add(f"{story['id']}/{clip['file']}")
    if not wanted:
        raise Failed("no clips referenced by stories.json — nothing to verify")
    listing = run(
        ["gcloud", "storage", "ls", "--recursive", f"gs://{bucket}/**"],
        cwd=REPO_ROOT,
        dry_run=False,
        capture=True,
        allow_failure=True,
    )
    prefix = f"gs://{bucket}/"
    present = {
        line.strip()[len(prefix):]
        for line in listing.splitlines()
        if line.strip().startswith(prefix)
    }
    missing = sorted(wanted - present)
    if missing:
        raise Failed(
            f"{len(missing)} clip(s) referenced by stories.json are NOT in the "
            f"bucket, e.g. {missing[0]} — families would see a Listen button "
            f"and hear nothing. Re-run with the upload step, or regenerate."
        )
    print(f"    ok: all {len(wanted)} referenced clips are in the bucket")


def copy_to_website(website_root: Path, dry_run: bool) -> None:
    targets = [
        (BUILT_SITE_DIR / "data" / "stories.json",
         website_root / "pilot" / "data" / "stories.json"),
        (BUILT_SITE_DIR / "explorer" / "index.html",
         website_root / "pilot" / "explorer" / "index.html"),
        (BUILT_SITE_DIR / "explorer" / "explorer.js",
         website_root / "pilot" / "explorer" / "explorer.js"),
    ]
    for source, destination in targets:
        if dry_run:
            print(f"    would copy {source.name} -> {destination}")
            continue
        if not source.is_file():
            raise Failed(f"expected build output missing: {source}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        print(f"    copied {source.name} -> {destination}")


def run_website_tests(website_root: Path, dry_run: bool) -> None:
    test_dir = website_root / WEBSITE_TEST_DIR
    if not test_dir.is_dir():
        print("    no pilot test directory — skipping")
        return
    for test_file in sorted(test_dir.glob("test_*.js")):
        relative = str(WEBSITE_TEST_DIR / test_file.name)
        output = run(
            ["node", relative],
            cwd=website_root,
            dry_run=dry_run,
            capture=True,
            allow_failure=True,
        )
        if dry_run:
            continue
        if "Cannot find module 'jsdom'" in output:
            print("    jsdom not installed (`npm i jsdom`) — skipping tests")
            return
        lines = [line for line in output.splitlines() if line.strip()]
        summary = lines[-1].strip() if lines else "(no output)"
        if "PASSED" not in summary:
            print(output)
            raise Failed(f"{relative} failed — not publishing a broken pilot")
        print(f"    {relative}: {summary}")


def commit_and_push(
    repo: Path, paths: list[str], message: str, dry_run: bool, push: bool
) -> bool:
    existing = [p for p in paths if (repo / p).exists()]
    if not existing:
        print(f"    nothing to stage in {repo.name}")
        return False
    run(["git", "add", *existing], cwd=repo, dry_run=dry_run)
    if dry_run:
        print(f"    would commit + {'push' if push else 'stop before push'}")
        return True
    staged = subprocess.run(
        ["git", "diff", "--cached", "--quiet", "--", *existing], cwd=repo
    )
    if staged.returncode == 0:
        print(f"    {repo.name}: no changes to commit")
        return False
    run(["git", "commit", "-m", message], cwd=repo, dry_run=False)
    if push:
        run(["git", "push"], cwd=repo, dry_run=False)
    else:
        print(f"    {repo.name}: committed, not pushed (--no-push)")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-m", "--message", help="commit message for both repos")
    parser.add_argument("--website", type=Path, default=DEFAULT_WEBSITE_ROOT,
                        help=f"buju_website checkout (default: {DEFAULT_WEBSITE_ROOT})")
    parser.add_argument("--dry-run", action="store_true",
                        help="print every command without changing anything")
    parser.add_argument("--no-push", action="store_true",
                        help="commit both repos but don't push")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()

    bucket = os.getenv("BUJU_PILOT_AUDIO_BUCKET", DEFAULT_AUDIO_BUCKET)
    website_root = args.website.expanduser().resolve()
    if not (website_root / "pilot").is_dir():
        raise Failed(f"{website_root} doesn't look like buju_website")

    stories = voiced_story_ids()
    print(f"publishing {len(stories)} voiced story(ies) to gs://{bucket}")
    for story_id in stories:
        print(f"  · {story_id}")
    if args.dry_run:
        print("\n(dry run — nothing will change)")

    step(1, "Upload reviewed clips to the bucket")
    upload_clips(bucket, args.dry_run)

    step(2, "Rebuild pilot_site (stamps audio into stories.json)")
    voiced = rebuild_site(args.dry_run)
    if not args.dry_run:
        print(f"    {voiced} voiced story(ies) stamped")

    step(3, "Verify every referenced clip is in the bucket")
    verify_bucket_coverage(bucket, args.dry_run)

    step(4, "Copy data + explorer into buju_website")
    copy_to_website(website_root, args.dry_run)

    step(5, "Run the pilot test suites")
    if args.skip_tests:
        print("    skipped (--skip-tests)")
    else:
        run_website_tests(website_root, args.dry_run)

    step(6, "Commit and push both repos")
    message = args.message or (
        f"Publish narration audio for {len(stories)} pilot story(ies)\n\n"
        + "\n".join(f"  {s}" for s in stories)
    )
    push = not args.no_push
    commit_and_push(REPO_ROOT, DATASTORE_COMMIT_PATHS, message, args.dry_run, push)
    commit_and_push(website_root, WEBSITE_COMMIT_PATHS, message, args.dry_run, push)

    print(
        "\n\033[1mDone.\033[0m"
        + ("" if push else " (nothing pushed — run git push in both repos)")
        + "\nVercel redeploys on the website push; then open a voiced story on "
        "buju.ai/pilot and tap Listen."
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Failed as failure:
        print(f"\n\033[31mstopped:\033[0m {failure}", file=sys.stderr)
        sys.exit(1)
