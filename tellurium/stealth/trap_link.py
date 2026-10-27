"""Trap links: links a person could not see or click right now, or that wear a honeypot marker.

A crawler that follows every ``<a href>`` of a page also follows the ones a site
hides from people to catch bots. :func:`reasons` reads, in one call in the tab's
isolated world (page JS can neither patch what it reads nor see the call), the
link's computed style, its boxes, its ancestors and its attributes, and names the
signals that fired:

``not-rendered``
    no box: ``display: none`` on it or an ancestor, or inside a closed
    ``<details>`` (a link of a closed menu is a trap too: a person does not click it
    without opening the menu first);
``visibility-hidden``, ``transparent``
    ``visibility`` other than ``visible``; ``opacity: 0`` on it or an ancestor;
``no-pointer``, ``inert``, ``aria-hidden``
    ``pointer-events: none``; inside an ``inert`` subtree; ``aria-hidden="true"``
    on it or an ancestor while it can still be clicked;
``zero-size``
    less than 2 CSS px wide or tall, its overflowing content included unless it
    clips it;
``off-page``
    wholly outside the scrollable document (``left: -9999px``), or outside the
    viewport when ``position: fixed``; below the fold is not off-page;
``clipped``
    nothing of it left inside the boxes of the ancestors that clip it
    (``overflow: hidden``, ``clip``, ``clip-path: inset()``);
``empty``
    nothing a person could see in its box: no text, no image, icon, pseudo-element
    content, background image or color, border;
``same-color``
    all its visible text is transparent or the color of the background behind it;
``honeypot-marker``
    ``honeypot`` (also ``honey-pot``, ``honey_pot``) in its ``id``, ``class`` or ``name``;
``nofollow``
    ``rel="nofollow"``, reported only next to another signal: alone it is a
    normal link.

A link moved off the page or clipped away that a ``:focus`` rule brings back
(a "skip to content" link) is not a trap. The check is conservative and has no
thresholds to tune: better to skip a closed menu's link than to click a trap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tellurium.browser.handles import handles_of, send_on_handle
from tellurium.cdp.types import CDPError

if TYPE_CHECKING:
    from tellurium.browser.element import Element

# Run with ``this`` bound to the link, in the isolated world; returns the signals.
_REASONS_JS = r"""
function () {
    const el = this, doc = el.ownerDocument, win = doc.defaultView;
    const MIN = 2, SAME = 3, CAP = 200;
    const css = (n, pseudo) => win.getComputedStyle(n, pseudo);
    const up = (n) => n.assignedSlot || n.parentElement || n.getRootNode().host || null;
    const chain = [];
    for (let n = el; n; n = up(n)) chain.push(n);
    const out = [];
    if (chain.some((n) => n.getAttribute('aria-hidden') === 'true')) out.push('aria-hidden');
    if (chain.some((n) => n.hasAttribute('inert'))) out.push('inert');
    const marker = /honey[-_]?pot/i;
    if (['id', 'class', 'name'].some((a) => marker.test(el.getAttribute(a) || ''))) {
        out.push('honeypot-marker');
    }
    const finish = () => {
        if (out.length && /(^|\s)nofollow(\s|$)/i.test(el.getAttribute('rel') || '')) {
            out.push('nofollow');
        }
        return out;
    };
    const shown = el.checkVisibility ? el.checkVisibility() : true;
    if (!shown || el.getClientRects().length === 0) {
        out.push('not-rendered');
        return finish();
    }
    const own = css(el);
    if (own.visibility !== 'visible') out.push('visibility-hidden');
    if (chain.some((n) => parseFloat(css(n).opacity) === 0)) out.push('transparent');
    if (own.pointerEvents === 'none') out.push('no-pointer');

    const rect = (r) => ({l: r.left, t: r.top, r: r.right, b: r.bottom});
    const small = (a) => a.r - a.l < MIN || a.b - a.t < MIN;
    const meet = (a, b) => ({
        l: Math.max(a.l, b.l), t: Math.max(a.t, b.t),
        r: Math.min(a.r, b.r), b: Math.min(a.b, b.b),
    });
    const clips = (v) => v === 'hidden' || v === 'clip';
    const box = el.getBoundingClientRect();
    const area = rect(box);
    const range = doc.createRange();
    range.selectNodeContents(el);
    for (const r of range.getClientRects()) {
        if (r.width <= 0 && r.height <= 0) continue;
        if (!clips(own.overflowX)) { area.l = Math.min(area.l, r.left); area.r = Math.max(area.r, r.right); }
        if (!clips(own.overflowY)) { area.t = Math.min(area.t, r.top); area.b = Math.max(area.b, r.bottom); }
    }
    const length = (v, whole) => (v.endsWith('%') ? (parseFloat(v) / 100) * whole : parseFloat(v) || 0);
    const shape = (n, s, vis) => {
        const r = n.getBoundingClientRect();
        if (s.clip && s.clip.startsWith('rect(') && (s.position === 'absolute' || s.position === 'fixed')) {
            const [t, rr, b, l] = s.clip.slice(5, -1).split(/[\s,]+/);
            const at = (v, auto) => (v === 'auto' ? auto : parseFloat(v));
            vis = meet(vis, {
                l: r.left + at(l, 0), t: r.top + at(t, 0),
                r: r.left + at(rr, r.width), b: r.top + at(b, r.height),
            });
        }
        if (s.clipPath && s.clipPath.startsWith('inset(')) {
            const v = s.clipPath.slice(6, -1).split(' round ')[0].trim().split(/\s+/);
            const [t, rr = t, b = t, l = rr] = v;
            vis = meet(vis, {
                l: r.left + length(l, r.width), t: r.top + length(t, r.height),
                r: r.right - length(rr, r.width), b: r.bottom - length(b, r.height),
            });
        }
        return vis;
    };
    let vis = shape(el, own, {...area});
    let abs = own.position === 'absolute', fixed = own.position === 'fixed';
    for (let n = up(el); n && !fixed; n = up(n)) {
        const s = css(n);
        if (s.display === 'contents') continue;
        const positioned = s.position !== 'static';
        if (abs && !positioned) continue;
        if (n !== doc.documentElement && n !== doc.body) {
            const r = n.getBoundingClientRect();
            if (clips(s.overflowX)) { vis.l = Math.max(vis.l, r.left); vis.r = Math.min(vis.r, r.right); }
            if (clips(s.overflowY)) { vis.t = Math.max(vis.t, r.top); vis.b = Math.min(vis.b, r.bottom); }
        }
        vis = shape(n, s, vis);
        abs = s.position === 'absolute';
        fixed = s.position === 'fixed';
    }
    const pinned = chain.some((n) => css(n).position === 'fixed');
    const page = doc.scrollingElement || doc.documentElement;
    const dx = pinned ? 0 : win.scrollX, dy = pinned ? 0 : win.scrollY;
    const width = pinned ? win.innerWidth : Math.max(page.scrollWidth, win.innerWidth);
    const height = pinned ? win.innerHeight : Math.max(page.scrollHeight, win.innerHeight);
    let geometry = null;
    if (small(area)) geometry = 'zero-size';
    else if (area.r + dx <= 0 || area.b + dy <= 0 || area.l + dx >= width || area.t + dy >= height) {
        geometry = 'off-page';
    } else if (small(vis)) geometry = 'clipped';

    const hidden = geometry || out.includes('transparent');
    if (hidden && revealedOnFocus()) {
        const i = out.indexOf('transparent');
        if (i >= 0) out.splice(i, 1);
        return finish();
    }
    if (geometry) out.push(geometry);
    if (geometry || out.includes('visibility-hidden') || out.includes('transparent')) {
        return finish();  // nothing of it to see: what it holds does not matter
    }

    const rgba = (c) => {
        const m = /^rgba?\(([^)]*)\)$/.exec(c || '');
        if (!m) return null;
        const p = m[1].split(/[\s,\/]+/).filter(Boolean).map(Number);
        if (p.length < 3 || p.some(isNaN)) return null;
        return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
    };
    const sees = (r) => r.width > 0 && r.height > 0 && !small(meet(rect(r), vis));
    const runs = [];
    const walker = doc.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for (let i = 0; i < CAP && walker.nextNode(); i++) {
        const node = walker.currentNode, parent = node.parentElement;
        if (!node.data.trim() || !parent) continue;
        if (css(parent).visibility !== 'visible' || (parent.checkVisibility && !parent.checkVisibility())) continue;
        range.selectNodeContents(node);
        if ([...range.getClientRects()].some(sees)) runs.push(parent);
    }
    const nodes = [el, ...[...el.querySelectorAll('*')].slice(0, CAP)];
    const graphic = /^(img|svg|picture|video|canvas|object|embed|iframe|input|select|textarea|button)$/;
    let marks = false, boxes = false;
    for (const n of nodes) {
        if (n !== el && (n.checkVisibility && !n.checkVisibility())) continue;
        if (n !== el && !sees(n.getBoundingClientRect())) continue;
        const s = css(n);
        if (n !== el && graphic.test(n.localName)) { marks = true; break; }
        const pseudo = ['::before', '::after'].some((p) => !['none', 'normal'].includes(css(n, p).content));
        const border = ['Top', 'Right', 'Bottom', 'Left'].some((side) => (
            parseFloat(s['border' + side + 'Width']) > 0 && s['border' + side + 'Style'] !== 'none'
            && (rgba(s['border' + side + 'Color']) || [0, 0, 0, 1])[3] > 0
        ));
        if (s.backgroundImage !== 'none' || pseudo || border) { marks = true; break; }
        if ((rgba(s.backgroundColor) || [0, 0, 0, 1])[3] > 0) boxes = true;
    }
    if (!runs.length && !marks && !boxes) {
        out.push('empty');
        return finish();
    }
    const backdrop = (n) => {
        for (; n; n = up(n)) {
            const s = css(n);
            if (s.backgroundImage !== 'none') return null;
            const c = rgba(s.backgroundColor);
            if (!c) return null;
            if (c[3] === 0) continue;
            return c[3] === 1 ? c : null;
        }
        return /dark/.test(css(doc.documentElement).colorScheme) ? null : [255, 255, 255, 1];
    };
    const unseen = (n) => {
        const s = css(n), c = rgba(s.webkitTextFillColor || s.color);
        if (!c) return false;
        if (c[3] === 0) return true;
        if (s.textShadow !== 'none' || parseFloat(s.webkitTextStrokeWidth) > 0) return false;
        const b = backdrop(n);
        return !!b && [0, 1, 2].every((i) => Math.abs(c[i] - b[i]) <= SAME);
    };
    if (runs.length && !marks && runs.every(unseen)) out.push('same-color');
    return finish();

    function revealedOnFocus() {
        const focus = /:focus(-visible|-within)?/g;
        const props = [
            'position', 'left', 'top', 'right', 'bottom', 'transform', 'translate', 'scale',
            'clip', 'clip-path', 'width', 'height', 'opacity', 'margin-left', 'margin-top',
            'text-indent', 'overflow',
        ];
        let budget = 10000;
        const scan = (rules) => {
            for (const rule of rules) {
                if (--budget < 0) return false;
                if (!rule.selectorText) {
                    if (rule.cssRules && scan(rule.cssRules)) return true;
                    continue;
                }
                if (!rule.selectorText.includes(':focus')) continue;
                if (!props.some((p) => rule.style.getPropertyValue(p))) continue;
                for (const part of rule.selectorText.split(',')) {
                    if (!part.includes(':focus')) continue;
                    try {
                        if (el.matches(part.replace(focus, '') || '*')) return true;
                    } catch (e) { /* a selector matches() cannot take */ }
                }
            }
            return false;
        };
        const root = el.getRootNode();
        const sheets = [...doc.styleSheets, ...(doc.adoptedStyleSheets || [])];
        if (root !== doc) sheets.push(...(root.styleSheets || []), ...(root.adoptedStyleSheets || []));
        for (const sheet of sheets) {
            let rules;
            try { rules = sheet.cssRules; } catch (e) { continue; }  // cross-origin sheet
            if (rules && scan(rules)) return true;
        }
        return false;
    }
}
"""


async def reasons(element: Element) -> list[str]:
    """The trap signals of *element* (an ``<a>``) that fired; empty for a normal link.

    One ``Runtime.callFunctionOn`` in the isolated world of the element's frame; in
    the element's own world only when that frame has no isolated world.
    """
    session, tab = element._session, element._tab
    object_id = await element._resolve()
    target = await _isolated(element, object_id) or object_id
    call = {
        "objectId": target,
        "functionDeclaration": _REASONS_JS,
        "returnByValue": True,
    }
    try:
        answer = await send_on_handle(session, "Runtime.callFunctionOn", call)
    finally:
        if target != object_id and (handles := handles_of(tab)) is not None:
            handles.discard(target, session)
    remote = answer.get("result", {})
    if remote.get("subtype") == "error" or "exceptionDetails" in answer:
        raise RuntimeError(remote.get("description", "trap-link check failed"))
    return list(remote.get("value") or [])


async def is_trap_link(element: Element) -> bool:
    """Whether a person could not see or click *element* now, or it wears a honeypot marker."""
    return bool(await reasons(element))


async def _isolated(element: Element, object_id: str) -> str | None:
    """*element*'s node resolved in its frame's isolated world, or ``None``."""
    from tellurium.browser.refs import frame_world

    session, tab = element._session, element._tab
    if not hasattr(tab, "_hsim_worlds"):
        return None
    described = await send_on_handle(session, "DOM.describeNode", {"objectId": object_id})
    params = {"backendNodeId": described["node"]["backendNodeId"]}
    if (handles := handles_of(tab)) is not None:
        params["objectGroup"] = handles.name
    frame_id = await _frame_of(element)
    for _attempt in range(2):  # a world cached for a document that has gone: make a new one
        context = await frame_world(tab, session, frame_id)
        if context is None:
            return None
        try:
            resolved = await send_on_handle(
                session, "DOM.resolveNode", params | {"executionContextId": context}
            )
        except CDPError:
            tab._hsim_worlds.pop(frame_id, None)
            continue
        return resolved["object"]["objectId"]
    return None


async def _frame_of(element: Element) -> str:
    """The frame the element's session addresses: the tab's, or an OOPIF's own root."""
    session, tab = element._session, element._tab
    if element._frame_id:
        return element._frame_id
    if session is tab._session:
        return tab._frame_id
    tree = await send_on_handle(session, "Page.getFrameTree", {})
    return str(tree["frameTree"]["frame"]["id"])
