"""The person's check as a web page: each sampled passage beside its page images, with
buttons that record the result as `python3 -m ocr check` does. Run on the machine that
holds the work directory, and open it from a phone or laptop:

    python3 -m ocr serve <work> [<work> ...] --by NAME --port 8090
"""
from __future__ import annotations

import html
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote
from urllib.request import urlopen

from ocr.gate import evaluate, record, start_check, text_hash
from ocr.work import WORK_ROOT, WorkConfig, WorkDir

# Page images, fetched once and served from here: a phone loading dozens of large scans
# straight from the Internet Archive stops getting them.
IMAGE_CACHE = WORK_ROOT / "_page_images"

STYLE = """
:root { color-scheme: light dark; }
body { font: 17px/1.5 Georgia, serif; margin: 0 auto; max-width: 1100px; padding: 16px; }
h1 { font-size: 22px; } h2 { font-size: 18px; margin-top: 2.5em; }
.pair { display: grid; grid-template-columns: 1fr; gap: 16px; }
@media (min-width: 900px) { .pair { grid-template-columns: 1fr 1fr; } }
.text { white-space: pre-wrap; }
img { width: 100%; border: 1px solid #8888; margin-bottom: 8px; }
.done { color: #2a7a2a; font-weight: bold; } .diff { color: #b3261e; font-weight: bold; }
button { font-size: 16px; padding: 8px 14px; margin: 6px 6px 6px 0; }
textarea { width: 100%; font-size: 16px; box-sizing: border-box; }
"""


def page_image(config: WorkConfig, leaf: int) -> str:
    return f"https://archive.org/download/{config.scan}/page/n{leaf}.jpg"


def cached_image(config: WorkConfig, leaf: int, cache: Path = IMAGE_CACHE) -> Path:
    path = cache / config.scan / f"n{leaf}.jpg"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        if config.pdf:
            # A PDF scan is not online: its page is drawn from the vendored file.
            from ocr.pdf import render_page
            from ocr.work import SOURCES
            render_page(SOURCES / config.pdf, leaf, dpi=200).convert("L").save(path, "JPEG", quality=85)
            return path
        with urlopen(page_image(config, leaf), timeout=60) as response:
            data = response.read()
        path.write_bytes(data)
    return path


def render(workdirs: list[WorkDir]) -> str:
    out = ["<!doctype html><meta charset=utf-8>",
           "<meta name=viewport content='width=device-width, initial-scale=1'>",
           f"<title>OCR check</title><style>{STYLE}</style>",
           "<h1>OCR check against the page images</h1>",
           "<p>Compare each passage with its page, word for word. The editor's summaries, "
           "comments and notes are left out on purpose, and so are the small note numbers "
           "in the text. Line breaks and italics do not matter.</p>"]
    for wd in workdirs:
        check = start_check(wd)
        result = evaluate(wd)
        note = f"<p>{html.escape(wd.config.check_note)}</p>" if wd.config.check_note else ""
        out.append(f"<h1>{html.escape(wd.config.title)}</h1>{note}"
                   f"<p>{result.checked} of {result.required} checked.</p>")
        passages = {p.id: p for p in wd.passages()}
        for e in check["sample"]:
            p = passages[e["id"]]
            state = ""
            if e["result"] == "matches":
                state = "<span class=done>Matches</span>"
            elif e["result"] == "differences":
                state = f"<span class=diff>Differs: {html.escape(e['differences'] or '')}</span>"
            images = "".join(f"<a href='/page/{wd.config.work}/{leaf}.jpg'>"
                             f"<img loading=lazy src='/page/{wd.config.work}/{leaf}.jpg'></a>"
                             for leaf in p.leaves)
            key = f"{html.escape(wd.config.work)}|{html.escape(p.id)}"
            out.append(
                f"<h2 id='{key}'>{html.escape(p.id)}, {html.escape(p.page_ref())} {state}</h2>"
                f"<div class=pair><div class=text>{html.escape(p.text)}</div><div>{images}</div></div>"
                f"<form method=post><input type=hidden name=key value='{key}'>"
                f"<input type=hidden name=shown value='{text_hash(p.text)}'>"
                "<button name=result value=matches>Matches</button>"
                "<details><summary>It differs</summary>"
                "<textarea name=what rows=2 placeholder='What differs'></textarea>"
                "<label><input type=checkbox name=wording> A word is wrong, missing or extra"
                "</label><br><button name=result value=differences>Save difference</button>"
                "</details></form>")
    return "\n".join(out)


def serve(workdirs: list[WorkDir], by: str, port: int) -> None:
    by_work = {wd.config.work: wd for wd in workdirs}
    # One check.json per work, read and rewritten whole, under a threaded server.
    recording = threading.Lock()
    for wd in workdirs:
        for leaf in {leaf for p in wd.passages()
                     if p.id in {e["id"] for e in start_check(wd)["sample"]} for leaf in p.leaves}:
            cached_image(wd.config, leaf)

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: str = "", location: str | None = None) -> None:
            data = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            if location:
                self.send_header("Location", location)
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            parts = self.path.strip("/").removesuffix(".jpg").split("/")
            if len(parts) == 3 and parts[0] == "page" and parts[1] in by_work \
                    and parts[2].isdigit():
                data = cached_image(by_work[parts[1]].config, int(parts[2])).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "max-age=86400")
                self.end_headers()
                self.wfile.write(data)
                return
            self._send(200, render(workdirs))

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", 0))
            form = parse_qs(self.rfile.read(length).decode(), keep_blank_values=True)
            work, _, passage = form["key"][0].partition("|")
            result = form["result"][0]
            what = form.get("what", [""])[0].strip() or None
            try:
                with recording:
                    record(by_work[work], passage, result, by, what, "wording" in form,
                           shown_sha256=form["shown"][0])
            except (KeyError, ValueError) as exc:
                self._send(400, html.escape(str(exc)))
                return
            self._send(303, location="/#" + quote(form["key"][0]))

        def log_message(self, *args) -> None:
            pass

    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
