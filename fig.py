#!/usr/bin/env python3
"""
fig.py — Figma from the terminal.

Reads a Figma personal access token from `.figma_token` in the script folder
(env var FIGMA_TOKEN takes precedence; `--token` flag overrides both).

Usage:
  python fig.py me
  python fig.py file FILE_KEY [--nodes 0:1,2:3] [--json] [--out file.json]
  python fig.py pages FILE_KEY
  python fig.py components FILE_KEY
  python fig.py styles FILE_KEY
  python fig.py comments FILE_KEY
  python fig.py export FILE_KEY --ids 0:1,2:3 [--format png] [--scale 2] [--out dir]
  python fig.py projects TEAM_ID
  python fig.py project-files PROJECT_ID
  python fig.py open FILE_KEY            # print the figma.com URL
  python fig.py save-token               # store token interactively (UTF-8 safe)

A personal access token is created at: Figma -> avatar menu -> Settings ->
Personal access tokens. "File content: read" scope is enough for everything
here; add "Comments: write" if you later post comments.
"""

import argparse
import json
import os
import sys
import time
import getpass
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE = "https://api.figma.com/v1"


def find_token(cli_token=None):
    if cli_token:
        return cli_token.strip()
    env = os.environ.get("FIGMA_TOKEN")
    if env:
        return env.strip()
    p = Path(__file__).resolve().parent / ".figma_token"
    if p.exists():
        t = p.read_text(encoding="utf-8").strip()
        if t:
            return t
    return None


def save_token_file():
    tok = getpass.getpass("Paste Figma personal access token (hidden): ").strip()
    if not tok:
        print("No token entered, nothing saved.", file=sys.stderr)
        sys.exit(1)
    p = Path(__file__).resolve().parent / ".figma_token"
    p.write_text(tok, encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    print(f"Saved to {p}")


def call(path, token, params=None, retries=5):
    url = BASE + path
    if params:
        url += "?" + "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())
    for attempt in range(retries):
        req = Request(url, headers={"X-Figma-Token": token})
        try:
            with urlopen(req, timeout=60) as resp:
                return json.load(resp)
        except HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:500]
            except Exception:
                pass
            if e.code in (401, 403):
                print(f"Auth failed ({e.code}). Token missing or invalid. "
                      f"Run `python fig.py save-token` or check token scopes.\n{body}",
                      file=sys.stderr)
                sys.exit(2)
            if e.code == 404:
                print(f"Not found ({e.code}). Check the key/id.\n{body}", file=sys.stderr)
                sys.exit(3)
            if e.code == 429:
                wait = int(e.headers.get("Retry-After", "60"))
                print(f"Rate limited, waiting {wait}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            if 500 <= e.code < 600 and attempt < retries - 1:
                wait = 5 * (2 ** attempt)
                print(f"Figma {e.code}, retrying in {wait}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            print(f"HTTP {e.code}: {body}", file=sys.stderr)
            sys.exit(4)
        except URLError as e:
            if attempt < retries - 1:
                wait = 5 * (2 ** attempt)
                print(f"Network error ({e.reason}), retrying in {wait}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            print(f"Network error: {e.reason}", file=sys.stderr)
            sys.exit(5)
    print("Request failed after retries.", file=sys.stderr)
    sys.exit(6)


def download(url, dest):
    req = Request(url, headers={"User-Agent": "fig-cli/1.0"})
    with urlopen(req, timeout=120) as resp, open(dest, "wb") as f:
        f.write(resp.read())


def walk(node, depth=0, max_depth=1):
    """Yield (depth, name, type, id) for a document subtree."""
    yield depth, node.get("name"), node.get("type"), node.get("id")
    if depth < max_depth:
        for child in node.get("children", []) or []:
            yield from walk(child, depth + 1, max_depth)


def cmd_me(token, args):
    r = call("/me", token)
    print(f"{r.get('handle')}  <{r.get('email')}>  (id {r.get('id')})")


def cmd_file(token, args):
    if args.nodes:
        r = call(f"/files/{args.file_key}/nodes", token,
                 {"ids": args.nodes})
        doc = {nid: n.get("document") for nid, n in r.get("nodes", {}).items()}
    else:
        r = call(f"/files/{args.file_key}", token)
        doc = r.get("document")
    out = json.dumps(doc if args.json else summarize(doc), indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(out)


def summarize(doc):
    """Top-level outline: pages -> top-level frames, without the full tree."""
    pages = []
    for page in (doc.get("children") or []):
        frames = [{"name": c.get("name"), "type": c.get("type"), "id": c.get("id")}
                  for c in (page.get("children") or [])]
        pages.append({"page": page.get("name"), "id": page.get("id"), "frames": frames})
    return pages


def cmd_pages(token, args):
    r = call(f"/files/{args.file_key}", token)
    for page in (r.get("document", {}).get("children") or []):
        print(f"{page.get('name')}  [{page.get('id')}]")


def cmd_components(token, args):
    r = call(f"/files/{args.file_key}/components", token)
    meta = r.get("meta", {})
    for key, c in (meta.get("components") or {}).items():
        pg = (c.get("containing_frame") or {}).get("name", "?")
        print(f"{c.get('name')}  [{key}]  (page: {pg})")


def cmd_styles(token, args):
    r = call(f"/files/{args.file_key}/styles", token)
    for key, s in (r.get("meta", {}).get("styles") or {}).items():
        print(f"{s.get('name')}  [{key}]  ({s.get('style_type')})")


def cmd_comments(token, args):
    r = call(f"/files/{args.file_key}/comments", token)
    for c in r.get("comments", []):
        u = (c.get("user") or {}).get("handle", "?")
        msg = (c.get("message") or "").replace("\n", " ")[:120]
        ts = (c.get("created_at") or "")[:10]
        print(f"[{ts}] {u}: {msg}")
        for reply in c.get("replies") or []:
            ru = (reply.get("user") or {}).get("handle", "?")
            rmsg = (reply.get("message") or "").replace("\n", " ")[:120]
            print(f"      ↳ {ru}: {rmsg}")


def cmd_export(token, args):
    ids = [i.strip() for i in args.ids.split(",") if i.strip()]
    if not ids:
        print("Pass at least one node id via --ids", file=sys.stderr)
        sys.exit(1)
    r = call(f"/images/{args.file_key}", token, {
        "ids": ",".join(ids),
        "format": args.format,
        "scale": args.scale,
    })
    outdir = Path(args.out or ".")
    outdir.mkdir(parents=True, exist_ok=True)
    images = r.get("images", {})
    n = 0
    for nid in ids:
        url = images.get(nid)
        if not url:
            print(f"skip {nid}: no image returned", file=sys.stderr)
            continue
        fname = f"{nid.replace(':', '_')}.{args.format}"
        dest = outdir / fname
        try:
            download(url, dest)
            print(f"saved {dest}")
            n += 1
        except Exception as e:
            print(f"failed {nid}: {e}", file=sys.stderr)
    print(f"done: {n}/{len(ids)} exported")


def cmd_projects(token, args):
    r = call(f"/teams/{args.team_id}/projects", token)
    for p in r.get("projects", []):
        print(f"{p.get('name')}  [{p.get('id')}]")


def cmd_project_files(token, args):
    r = call(f"/projects/{args.project_id}/files", token)
    for f in r.get("files", []):
        print(f"{f.get('name')}  [{f.get('key')}]  (last modified {f.get('last_modified','')[:10]})")


def cmd_open(token, args):
    print(f"https://www.figma.com/design/{args.file_key}/")


def build_parser():
    p = argparse.ArgumentParser(prog="fig.py", description="Figma from the terminal.")
    p.add_argument("--token", help="personal access token (overrides file/env)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("me", help="show the token owner")
    s.set_defaults(fn=cmd_me)

    s = sub.add_parser("file", help="fetch file document (outline or full JSON)")
    s.add_argument("file_key")
    s.add_argument("--nodes", help="comma-separated node ids, e.g. 0:1,2:3")
    s.add_argument("--json", action="store_true", help="dump full JSON instead of outline")
    s.add_argument("--out", help="write to file instead of stdout")
    s.set_defaults(fn=cmd_file)

    s = sub.add_parser("pages", help="list pages in a file")
    s.add_argument("file_key")
    s.set_defaults(fn=cmd_pages)

    s = sub.add_parser("components", help="list components in a file")
    s.add_argument("file_key")
    s.set_defaults(fn=cmd_components)

    s = sub.add_parser("styles", help="list styles in a file")
    s.add_argument("file_key")
    s.set_defaults(fn=cmd_styles)

    s = sub.add_parser("comments", help="list comments on a file")
    s.add_argument("file_key")
    s.set_defaults(fn=cmd_comments)

    s = sub.add_parser("export", help="export node(s) as image(s)")
    s.add_argument("file_key")
    s.add_argument("--ids", required=True, help="comma-separated node ids, e.g. 0:1,2:3")
    s.add_argument("--format", default="png", choices=["png", "jpg", "svg", "pdf"])
    s.add_argument("--scale", default=2, type=int, choices=[1, 2, 3, 4])
    s.add_argument("--out", default=".", help="output directory")
    s.set_defaults(fn=cmd_export)

    s = sub.add_parser("projects", help="list projects in a team")
    s.add_argument("team_id")
    s.set_defaults(fn=cmd_projects)

    s = sub.add_parser("project-files", help="list files in a project")
    s.add_argument("project_id")
    s.set_defaults(fn=cmd_project_files)

    s = sub.add_parser("open", help="print the figma.com URL for a file key")
    s.add_argument("file_key")
    s.set_defaults(fn=cmd_open)

    s = sub.add_parser("save-token", help="store token to .figma_token interactively")
    s.set_defaults(fn=lambda token, args: save_token_file())

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.cmd == "save-token":
        save_token_file()
        return
    if args.cmd == "open":
        cmd_open(None, args)
        return
    token = find_token(args.token)
    if not token:
        print("No Figma token found. Run `python fig.py save-token`, set FIGMA_TOKEN, "
              "or pass --token.", file=sys.stderr)
        sys.exit(2)
    args.fn(token, args)


if __name__ == "__main__":
    main()
