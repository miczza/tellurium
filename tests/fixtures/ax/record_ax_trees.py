"""Record the AX trees the snapshot unit tests run on.

Run from the repo root (needs Chrome; ``xvfb-run -a`` without a display)::

    .venv/bin/python tests/fixtures/ax/record_ax_trees.py

It serves ``tests/integration/fixtures`` locally, fetches each page's tree with
:func:`tellurium.browser.snapshot.fetch_tree` and writes it here, trimmed to the
fields the snapshot reads.
"""

from __future__ import annotations

import asyncio
import functools
import http.server
import json
import threading
from pathlib import Path

from tellurium import Browser
from tellurium.browser.snapshot import AXTree, fetch_tree

HERE = Path(__file__).parent
PAGES = Path(__file__).parents[2] / "integration" / "fixtures"
# name of the recording -> page (served as a.test, whose frames may load b.test)
RECORDINGS = {
    "form": "snapshot_form.html",
    "iframe": "snapshot_iframe.html",
    "oopif": "snapshot_oopif.html",
}
_KEPT = ("nodeId", "ignored", "childIds", "backendDOMNodeId", "parentId")


def _trim_node(node: dict) -> dict:
    out = {key: node[key] for key in _KEPT if key in node}
    for key in ("role", "name", "value"):
        if key in node:
            out[key] = {"value": node[key].get("value")}
    props = [
        {"name": p["name"], "value": {"value": p.get("value", {}).get("value")}}
        for p in node.get("properties", [])
    ]
    if props:
        out["properties"] = props
    return out


def _trim(tree: AXTree) -> AXTree:
    frames = {k: v if isinstance(v, str) else _trim(v) for k, v in tree.frames.items()}
    return AXTree(nodes=[_trim_node(n) for n in tree.nodes], frames=frames)


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def _serve() -> tuple[http.server.ThreadingHTTPServer, int]:
    handler = functools.partial(_QuietHandler, directory=str(PAGES))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


async def main() -> None:
    server, port = _serve()
    browser = await Browser.launch(
        headless=True, args=["--host-resolver-rules=MAP *.test 127.0.0.1"]
    )
    try:
        tab = browser.main_tab
        for name, page in RECORDINGS.items():
            await tab.get(f"http://a.test:{port}/{page}")
            tree = _trim(await fetch_tree(tab._session))
            # the port changes on every run: keep the recordings stable
            text = json.dumps(tree.to_json(), indent=1, ensure_ascii=False)
            (HERE / f"{name}.json").write_text(text.replace(f":{port}/", ":8000/") + "\n")
            print(f"recorded {name}: {len(tree.nodes)} nodes")
    finally:
        await browser.close()
        server.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
