"""
Publish the pilot library to the website repo, end to end.

    python scripts/publish_pilot.py                    # full run
    python scripts/publish_pilot.py --dry-run          # show, do nothing
    python scripts/publish_pilot.py --website ../buju_website

The steps, in order, stopping at the first failure:

  1. build_story_explorer.py --check   -- every story structurally valid
  2. build_pilot_site.py               -- rebuild explorer + pilot_site/
  3. copy pilot_site/data/stories.json -> <website>/pilot/data/
     copy pilot_site/explorer/*        -> <website>/pilot/explorer/
  4. node tests/pilot/*.js             -- the jsdom suites, in the website repo

Nothing here touches audio, git, or Vercel. After a green run you still
have to commit + push the website repo, and set BUJU_PILOT_FAMILIES for any
new family (an env change needs a redeploy to reach the edge middleware).

Run as a script from the repo root, not `python -m`: the package's logging/
subpackage would shadow stdlib logging.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PILOT_SITE = REPO_ROOT / "story_definitions" / "preview" / "pilot_site"


def step(number: int, title: str) -> None:
    print(f"\n=== {number}. {title} " + "=" * max(0, 56 - len(title)))


def run(command: list[str], cwd: Path, dry_run: bool) -> None:
    printable = " ".join(command)
    if dry_run:
        print(f"  would run: {printable}   (in {cwd})")
        return
    print(f"  $ {printable}")
    result = subprocess.run(command, cwd=cwd)
    if result.returncode != 0:
        raise SystemExit(f"\nFAILED: {printable} (exit {result.returncode})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--website", default=str(REPO_ROOT.parent / "buju_website"),
        help="path to the buju_website repo (default: ../buju_website)",
    )
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    website = Path(args.website).expanduser().resolve()
    if not (website / "pilot").is_dir():
        raise SystemExit(f"no pilot/ directory under {website} -- wrong --website?")

    step(1, "validate the library")
    run([sys.executable, "scripts/build_story_explorer.py", "--check"],
        REPO_ROOT, args.dry_run)

    step(2, "rebuild pilot_site")
    run([sys.executable, "scripts/build_pilot_site.py"], REPO_ROOT, args.dry_run)

    step(3, f"copy into {website.name}")
    data_src = PILOT_SITE / "data" / "stories.json"
    explorer_src = sorted((PILOT_SITE / "explorer").glob("*"))
    if not args.dry_run and not data_src.is_file():
        raise SystemExit(f"missing {data_src} -- did step 2 run?")

    copies = [(data_src, website / "pilot" / "data" / data_src.name)]
    copies += [(p, website / "pilot" / "explorer" / p.name) for p in explorer_src]
    for src, dst in copies:
        print(f"  {'would copy' if args.dry_run else 'copied'}  "
              f"{src.name} -> {dst.relative_to(website)}")
        if not args.dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    if not args.dry_run:
        payload = json.loads((website / "pilot" / "data" / "stories.json").read_text())
        bands: dict[str, int] = {}
        for story in payload["stories"]:
            bands[story["age_band"]] = bands.get(story["age_band"], 0) + 1
        voiced = sum(1 for s in payload["stories"] if s.get("audio"))
        print(f"\n  {len(payload['stories'])} stories "
              f"({voiced} voiced), {len(payload['graph']['nodes'])} topics")
        for band in sorted(bands, key=lambda b: int(b.split("-")[0])):
            print(f"    {band:>5}: {bands[band]}")

    if args.skip_tests:
        print("\n(skipping the website test suites)")
    else:
        step(4, "website test suites")
        if shutil.which("node") is None:
            print("  node not found on PATH -- skipping (run them yourself)")
        else:
            for test in sorted((website / "tests" / "pilot").glob("test_*.js")):
                run(["node", str(test.relative_to(website))], website, args.dry_run)

    print("\ndone. still to do by hand:")
    print(f"  * commit + push {website.name} (Vercel auto-deploys)")
    print("  * BUJU_PILOT_FAMILIES in Vercel for any new family "
          "(env change needs a redeploy)")
    print("  * audio, if these stories should be voiced, is a separate pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
