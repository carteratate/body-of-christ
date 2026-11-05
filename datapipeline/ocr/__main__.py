"""OCR clean-up tool (corpus-cleanup item 1.2f). Run from datapipeline/:

    python3 -m ocr clean   <work>             # furniture out, passages written
    python3 -m ocr correct <work>             # model correction, within the work's ceiling
    python3 -m ocr fix     <work>             # apply ocr/works/<work>.fixes.json
    python3 -m ocr sample  <work>             # draw the person's sample (once)
    python3 -m ocr check   <work> <passage> matches --by NAME
    python3 -m ocr check   <work> <passage> differences --by NAME --what "..." [--wording]
    python3 -m ocr serve   <work> [...] --by NAME --port N   # the check as a web page
    python3 -m ocr gate    <work>             # evaluate and write ocr_work/<work>/gate.md
    python3 -m ocr freeze  <work>             # write the final text to ocr/texts/<work>.json

<work> names `ocr/works/<work>.json`. `correct` calls the provider and spends money.
"""
from __future__ import annotations

import argparse
import sys

from ocr.work import WorkConfig, WorkDir


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m ocr", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("clean", "correct", "fix", "sample", "check", "gate", "freeze"):
        p = sub.add_parser(name)
        p.add_argument("work")
        if name == "clean":
            p.add_argument("--force", action="store_true", help="replace corrected passages")
        if name == "correct":
            p.add_argument("--redo", action="store_true", help="correct every passage again")
        if name == "sample":
            p.add_argument("--seed", type=int)
            p.add_argument("--redraw", action="store_true")
        if name == "check":
            p.add_argument("passage")
            p.add_argument("result", choices=("matches", "differences"))
            p.add_argument("--by", required=True)
            p.add_argument("--what", help="the differences found")
            p.add_argument("--wording", action="store_true", help="the differences change wording")
    serve = sub.add_parser("serve")
    serve.add_argument("works", nargs="+")
    serve.add_argument("--by", required=True)
    serve.add_argument("--port", type=int, default=8090)
    args = ap.parse_args(argv)
    if args.command == "serve":
        from ocr.serve import serve as run_server
        run_server([WorkDir(WorkConfig.load(w)) for w in args.works], args.by, args.port)
        return 0
    workdir = WorkDir(WorkConfig.load(args.work))

    if args.command == "clean":
        from ocr.furniture import clean_work
        r = clean_work(workdir, force=args.force)
        print(f"{len(workdir.passages())} passages, {len(r.removals)} removals, "
              f"{len(r.hyphens)} line-end breaks, {len(r.notes)} note blocks")
    elif args.command == "correct":
        from ocr.correct import AnthropicCorrector, run_correction
        res = run_correction(workdir, AnthropicCorrector(workdir.config.model),
                             workdir.config.ceiling_usd, redo=args.redo)
        r = res.run
        print(f"run {r['run']}: {r['calls']} calls, ${r['cost_usd']:.4f}; "
              f"work total ${workdir.spent_usd():.4f} of ${workdir.config.ceiling_usd:.2f}"
              + (f"; stopped: {r['stopped']}" if r["stopped"] else ""))
        return 1 if r["stopped"] else 0
    elif args.command == "fix":
        from ocr.fixes import apply_fixes
        print(f"{apply_fixes(workdir)} fixes applied")
    elif args.command == "freeze":
        from ocr.fixes import freeze
        print(freeze(workdir))
    elif args.command == "sample":
        from ocr.gate import start_check
        c = start_check(workdir, seed=args.seed, redraw=args.redraw)
        print(f"seed {c['seed']}: " + ", ".join(e["id"] for e in c["sample"]))
    elif args.command == "check":
        from ocr.gate import record
        record(workdir, args.passage, args.result, args.by, args.what, args.wording)
    elif args.command == "gate":
        from ocr.report import write
        _, result = write(workdir)
        print(f"{result.status}: " + ("; ".join(result.reasons) or "all checks pass"))
        print(workdir.file("gate.md"))
        return 0 if result.status == "pass" else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
