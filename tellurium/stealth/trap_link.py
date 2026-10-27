"""Trap links: links a person could not see or click right now, or that wear a honeypot marker.

A crawler that follows every ``<a href>`` of a page also follows the ones a site
hides from people to catch bots. :func:`reasons` reads, in the tab's isolated world
(page JS can neither patch what it reads nor see the call), the link's computed
style, boxes, ancestors and attributes, and names the signals that fired:

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
    wholly outside what scrolling can reach, through every box that scrolls it,
    inner to outer (``left: -9999px``); outside the viewport when ``position:
    fixed`` or along an axis the page does not scroll (``overflow: hidden`` on the
    root, as while a modal is open). Below the fold of the page or of an app's own
    scroll box, a slide further along a carousel: not off-page;
``clipped``
    nothing of it left inside the boxes of the ancestors that clip it
    (``overflow: hidden``, ``clip``, a ``clip-path`` basic shape: ``inset()``,
    ``circle(0)``, ``ellipse()``, a ``polygon()`` of no area);
``empty``
    nothing a person could see in its box: no text, no image, icon, pseudo-element
    content, background image or color, border;
``same-color``
    all its visible text is transparent or the color of the background behind it,
    when that background is known: never over an image, a gradient, a positioned
    ``::before``/``::after`` overlay or another element painting under the text;
``honeypot-marker``
    ``honeypot`` (also ``honey-pot``, ``honey_pot``) in its ``id``, ``class`` or ``name``;
``nofollow``
    ``rel="nofollow"``, reported only next to another signal: alone it is a
    normal link.

A hidden link (off the page, clipped away, transparent) in sight while Chrome
forces ``:focus`` on it, as a "skip to content" link, is not a trap: the focused
state is measured, not the rules. With a transition or an animation on the way, or
out of the tab order, it stays one. Conservative, with no thresholds to tune: better
to skip a closed menu's link than to click a trap.
"""

from __future__ import annotations

import asyncio
import contextlib
import weakref
from typing import TYPE_CHECKING, Any

from tellurium.browser.handles import handles_of, send_on_handle
from tellurium.cdp.types import CDPError

if TYPE_CHECKING:
    from tellurium.browser.element import Element
    from tellurium.cdp.transport._session import Session

# One forced-focus check at a time per CDP session (CSS.disable ends them all).
_FOCUS_LOCKS: weakref.WeakKeyDictionary[Session, asyncio.Lock] = weakref.WeakKeyDictionary()

# Run with ``this`` bound to the link, in the isolated world; returns the signals.
_REASONS_JS = r"""
function (focused) {
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
    const finish = (list = out) => {
        if (list.length && /(^|\s)nofollow(\s|$)/i.test(el.getAttribute('rel') || '')) {
            list.push('nofollow');
        }
        return list;
    };
    const shown = el.checkVisibility ? el.checkVisibility() : true;
    if (!shown || el.getClientRects().length === 0) {
        if (focused) return {seen: false};
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
        l: Math.max(a.l, b.l), t: Math.max(a.t, b.t), r: Math.min(a.r, b.r), b: Math.min(a.b, b.b),
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
        const cut = clipShape(s.clipPath || 'none', r);
        return cut ? meet(vis, cut) : vis;
    };
    // The box a basic-shape clip-path leaves of r (viewport coordinates), or null when
    // it cannot tell (url(), path(), a position with offsets): then it clips nothing.
    function clipShape(value, r) {
        const m = /^(inset|circle|ellipse|polygon)\((.*)\)/.exec(value);
        if (!m) return null;
        const [, kind, args] = m;
        // Only plain px and % read: calc() and the like make the shape unknown.
        const exact = (v, whole) => (/^-?[\d.]+(e-?\d+)?(px|%)?$/.test(v || '') ? length(v, whole) : NaN);
        if (kind === 'inset') {
            const [t, rr = t, b = t, l = rr] = args.split(' round ')[0].trim().split(/\s+/);
            return {
                l: r.left + length(l, r.width), t: r.top + length(t, r.height),
                r: r.right - length(rr, r.width), b: r.bottom - length(b, r.height),
            };
        }
        if (kind === 'polygon') {
            const points = args.replace(/^\s*(nonzero|evenodd)\s*,/, '').split(',').map((p) => {
                const [x, y] = p.trim().split(/\s+/);
                return [r.left + exact(x, r.width), r.top + exact(y, r.height)];
            });
            if (points.some(([x, y]) => isNaN(x) || isNaN(y))) return null;
            let twice = 0;
            points.forEach(([x, y], i) => {
                const [nx, ny] = points[(i + 1) % points.length];
                twice += x * ny - nx * y;
            });
            if (Math.abs(twice) / 2 < MIN * MIN) return {l: r.left, t: r.top, r: r.left, b: r.top};
            const xs = points.map((p) => p[0]), ys = points.map((p) => p[1]);
            return {l: Math.min(...xs), t: Math.min(...ys), r: Math.max(...xs), b: Math.max(...ys)};
        }
        const [radii, at = '50% 50%'] = args.split(/(?:^|\s)at\s/);
        const centre = place(at.trim().split(/\s+/), r, exact);
        if (!centre) return null;
        const [cx, cy] = centre;
        const side = (v, near, far) => (
            v === 'farthest-side' ? far : v === 'closest-side' || !v ? near : null
        );
        const nearX = Math.min(cx - r.left, r.right - cx), farX = Math.max(cx - r.left, r.right - cx);
        const nearY = Math.min(cy - r.top, r.bottom - cy), farY = Math.max(cy - r.top, r.bottom - cy);
        const [a, b] = radii.trim().split(/\s+/).filter(Boolean);
        let rx, ry;
        if (kind === 'circle') {
            const keyed = side(a, Math.min(nearX, nearY), Math.max(farX, farY));
            rx = ry = keyed ?? exact(a, Math.hypot(r.width, r.height) / Math.SQRT2);
        } else {
            rx = side(a, nearX, farX) ?? exact(a, r.width);
            ry = side(b, nearY, farY) ?? exact(b, r.height);
        }
        if (isNaN(rx) || isNaN(ry) || isNaN(cx) || isNaN(cy)) return null;
        return {l: cx - rx, t: cy - ry, r: cx + rx, b: cy + ry};
    }
    // A clip-path position (one or two keywords or lengths) in viewport coordinates.
    function place(tokens, r, exact) {
        const word = {left: '0%', top: '0%', center: '50%', right: '100%', bottom: '100%'};
        if (tokens.length > 2) return null;
        let [x, y = 'center'] = tokens;
        if (['top', 'bottom'].includes(x) || ['left', 'right'].includes(y)) [x, y] = [y, x];
        return [r.left + exact(word[x] || x, r.width), r.top + exact(word[y] || y, r.height)];
    }
    // The boxes that hold the link, inner to outer. One that clips cuts what is left
    // of it; one that scrolls brings what lies in its scrollable overflow into its own
    // box (a slide of a carousel, a row below the fold of an app that scrolls in a box
    // of its own) and leaves out what lies before its scroll origin. The root comes last.
    const html = doc.documentElement, body = doc.body;
    const owner = css(html).overflowX === 'visible' && css(html).overflowY === 'visible' && body ? body : html;
    const scrolls = (v) => v === 'auto' || v === 'scroll';
    const axes = [['overflowX', 'l', 'r'], ['overflowY', 't', 'b']];
    // shift: how far scrolling the boxes would move the link, to place its text in vis.
    let vis = shape(el, own, {...area}), off = false;
    const shift = {l: 0, t: 0};
    const hold = (n, s) => {
        const r = n.getBoundingClientRect(), l = r.left + n.clientLeft, t = r.top + n.clientTop;
        const pad = {l, t, r: l + n.clientWidth, b: t + n.clientHeight};
        const x = s.direction === 'rtl' ? pad.r - n.scrollLeft - n.scrollWidth : l - n.scrollLeft;
        const span = {l: x, t: t - n.scrollTop, r: x + n.scrollWidth, b: t - n.scrollTop + n.scrollHeight};
        for (const [axis, lo, hi] of axes) {
            const scrolled = scrolls(s[axis]);
            if (!scrolled && !clips(s[axis])) continue;
            const room = scrolled ? span : pad;
            if (vis[hi] <= room[lo] || vis[lo] >= room[hi]) {
                if (scrolled || n === body) off = true;  // the page itself does not scroll there
                vis[hi] = vis[lo];
                continue;
            }
            const inside = Math.min(vis[hi], pad[hi]) - Math.max(vis[lo], pad[lo]);
            if (!scrolled || inside >= MIN) {
                vis[lo] = Math.max(vis[lo], pad[lo]);
                vis[hi] = Math.min(vis[hi], pad[hi]);
            } else {  // scrolled into view: as much of it as the box can show
                const from = Math.max(vis[lo], span[lo]), length = Math.min(vis[hi], span[hi]) - from;
                shift[lo] += pad[lo] - from;
                vis[lo] = pad[lo];
                vis[hi] = pad[lo] + Math.min(length, pad[hi] - pad[lo]);
            }
        }
    };
    let abs = own.position === 'absolute', fixed = own.position === 'fixed';
    for (let n = up(el); n && !fixed && !off && !small(vis); n = up(n)) {
        const s = css(n);
        if (s.display === 'contents') continue;
        const positioned = s.position !== 'static';
        if (abs && !positioned) continue;
        if (n !== html && n !== owner) hold(n, s);
        vis = shape(n, s, vis);
        abs = s.position === 'absolute';
        fixed = s.position === 'fixed';
    }
    // The page a person can scroll over, in viewport coordinates: the viewport alone
    // for a fixed box, or along an axis the root does not let scroll (overflow: hidden).
    const page = doc.scrollingElement || html, view = css(owner);
    const reach = (axis, scrolled, size, whole) => (
        fixed || clips(view[axis]) ? [0, size] : [-scrolled, Math.max(whole, size) - scrolled]
    );
    const [x0, x1] = reach('overflowX', win.scrollX, win.innerWidth, page.scrollWidth);
    const [y0, y1] = reach('overflowY', win.scrollY, win.innerHeight, page.scrollHeight);
    if (!off && !small(vis) && (vis.r <= x0 || vis.b <= y0 || vis.l >= x1 || vis.t >= y1)) off = true;
    let geometry = null;
    if (small(area)) geometry = 'zero-size';
    else if (off) geometry = 'off-page';
    else if (small(vis)) geometry = 'clipped';

    // Called again while Chrome forces :focus on the link: is it in sight then?
    if (focused) return {seen: !geometry && !out.includes('transparent')};
    const hidden = geometry || out.includes('transparent');
    if (hidden && mayReveal()) {  // Python looks at the focused state, then picks one
        const revealed = finish(out.filter((signal) => signal !== 'transparent'));
        if (geometry) out.push(geometry);
        return {reasons: finish(), revealed};
    }
    if (geometry) out.push(geometry);
    if (geometry || out.includes('visibility-hidden') || out.includes('transparent')) {
        return finish();  // nothing of it to see: what it holds does not matter
    }

    const rgba = (c) => {
        const p = ((/^rgba?\(([^)]*)\)$/.exec(c || '') || [])[1] || '').split(/[\s,\/]+/).filter(Boolean).map(Number);
        return p.length < 3 || p.some(isNaN) ? null : [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
    };
    const moved = (r) => ({l: r.l + shift.l, t: r.t + shift.t, r: r.r + shift.l, b: r.b + shift.t});
    const sees = (r) => r.width > 0 && r.height > 0 && !small(meet(moved(rect(r)), vis));
    const runs = [], glyphs = [];
    const walker = doc.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for (let i = 0; i < CAP && walker.nextNode(); i++) {
        const node = walker.currentNode, parent = node.parentElement;
        if (!node.data.trim() || !parent) continue;
        if (css(parent).visibility !== 'visible' || (parent.checkVisibility && !parent.checkVisibility())) continue;
        range.selectNodeContents(node);
        const seen = [...range.getClientRects()].filter(sees);
        if (seen.length) runs.push(parent);
        glyphs.push(...seen.map(rect));
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
    // A positioned ::before / ::after with a background: an overlay a hero paints.
    const shade = (n) => ['::before', '::after'].some((p) => {
        const s = css(n, p);
        return !['none', 'normal'].includes(s.content) && ['absolute', 'fixed'].includes(s.position)
            && (s.backgroundImage !== 'none' || (rgba(s.backgroundColor) || [0, 0, 0, 1])[3] > 0);
    });
    const backdrop = (n) => {
        for (; n; n = up(n)) {
            const s = css(n);
            if (s.backgroundImage !== 'none' || (n !== el && shade(n))) return null;
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
    // Something that is not an ancestor painting where the text is (a hero <img>
    // behind it, a panel): the background is not known, so the colors cannot be compared.
    const overlaid = () => {
        const mine = new Set(chain), under = backdrop(el);
        const tree = doc.createTreeWalker(doc.documentElement, NodeFilter.SHOW_ELEMENT);
        for (let n = tree.currentNode, left = 20000; n; n = tree.nextNode()) {
            if (--left < 0) return true;  // too much to look through: not known either
            if (mine.has(n) || el.contains(n)) continue;
            const b = rect(n.getBoundingClientRect());
            if (!glyphs.some((g) => !small(meet(g, b)))) continue;
            if (n.checkVisibility && !n.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})) continue;
            const s = css(n), c = rgba(s.backgroundColor) || [0, 0, 0, 1];
            const same = under && c[3] === 1 && [0, 1, 2].every((i) => Math.abs(c[i] - under[i]) <= SAME);
            if (graphic.test(n.localName) || s.backgroundImage !== 'none' || (c[3] > 0 && !same)) return true;
        }
        return false;
    };
    if (runs.length && !marks && runs.every(unseen) && !overlaid()) out.push('same-color');
    return finish();

    // Whether a :focus rule might bring the link back once a person tabs to it. Only a
    // hint: the focused state itself decides. Not with a transition or an animation on
    // the way (its events would reach the page), nor out of the tab order.
    function mayReveal() {
        const focus = /:focus(-visible|-within)?/g, animates = /^(transition|animation)/;
        if (el.tabIndex < 0) return false;
        let budget = 10000, found = false, moving = false;
        const hit = new Set([el]);
        const scan = (rules) => {
            for (const rule of rules) {
                if (--budget < 0 || moving) return;
                if (!rule.selectorText) {
                    if (rule.cssRules) scan(rule.cssRules);
                    continue;
                }
                if (!rule.selectorText.includes(':focus')) continue;
                const parts = rule.selectorText.split(',').filter((part) => part.includes(':focus'));
                const hits = chain.filter((n) => parts.some((part) => {
                    try {
                        return n.matches(part.replace(focus, '') || '*');
                    } catch (e) { return false; }  // a selector matches() cannot take
                }));
                if (!hits.length) continue;
                hits.forEach((n) => hit.add(n));
                found = true;
                moving = [...rule.style].some((name) => animates.test(name));
            }
        };
        const root = el.getRootNode();
        const sheets = [...doc.styleSheets, ...(doc.adoptedStyleSheets || [])];
        if (root !== doc) sheets.push(...(root.styleSheets || []), ...(root.adoptedStyleSheets || []));
        for (const sheet of sheets) {
            let rules;
            try { rules = sheet.cssRules; } catch (e) { continue; }  // cross-origin sheet
            if (rules) scan(rules);
        }
        // Too many rules to read through: the focused state alone decides.
        return (found || budget < 0) && !moving && ![...hit].some((n) => {
            const s = css(n);
            return s.animationName !== 'none' || s.transitionDuration.split(',').some(parseFloat);
        });
    }
}
"""


class NoIsolatedWorldError(RuntimeError):
    """The link's frame has no isolated world, so the check would be visible to the page."""


async def reasons(element: Element) -> list[str]:
    """The trap signals of *element* (an ``<a>``) that fired; empty for a normal link.

    One ``Runtime.callFunctionOn`` in the isolated world of the element's frame, and a
    second one under a forced ``:focus`` when a focus rule might bring a hidden link back.
    :class:`NoIsolatedWorldError` when that frame has no isolated world: the check never
    runs where the page could see it.
    """
    session, tab = element._session, element._tab
    object_id = await element._resolve()
    target = await _isolated(element, object_id)
    if target is None:
        raise NoIsolatedWorldError("no isolated world in the link's frame: trap check not run")
    try:
        found = _value(await send_on_handle(session, "Runtime.callFunctionOn", _call(target)))
        if isinstance(found, dict):
            found = found["revealed"] if await _seen_focused(session, target) else found["reasons"]
    finally:
        if (handles := handles_of(tab)) is not None:
            handles.discard(target, session)
    return list(found or [])


def _call(target: str, *, focused: bool = False) -> dict:
    args = {"arguments": [{"value": focused}], "returnByValue": True}
    return {"objectId": target, "functionDeclaration": _REASONS_JS} | args


def _value(answer: dict) -> Any:
    remote = answer.get("result", {})
    if remote.get("subtype") == "error" or "exceptionDetails" in answer:
        raise RuntimeError(remote.get("description", "trap-link check failed"))
    return remote.get("value")


async def _seen_focused(session: Session, target: str) -> bool:
    """Whether the link is in sight while Chrome forces ``:focus`` and ``:focus-visible`` on it.

    ``CSS.forcePseudoState`` only changes which rules match: focus does not move, no focus or
    blur event fires, nothing scrolls. Force, measure and release go out back to back, so the
    state lasts one round trip; ``CSS.disable`` drops what is left. One at a time per session.
    """
    async with _FOCUS_LOCKS.setdefault(session, asyncio.Lock()):
        node = (await send_on_handle(session, "DOM.requestNode", {"objectId": target}))["nodeId"]
        await send_on_handle(session, "CSS.enable", {})
        try:
            force = {"nodeId": node, "forcedPseudoClasses": ["focus", "focus-visible"]}
            steps = [
                ("CSS.forcePseudoState", force),
                ("Runtime.callFunctionOn", _call(target, focused=True)),
                ("CSS.forcePseudoState", force | {"forcedPseudoClasses": []}),
            ]
            forced, answer, _ = await asyncio.gather(
                *(send_on_handle(session, method, params) for method, params in steps),
                return_exceptions=True,
            )
        finally:
            with contextlib.suppress(CDPError, TimeoutError, ConnectionError):
                await send_on_handle(session, "CSS.disable", {})
    if isinstance(answer, BaseException):
        raise answer
    return not isinstance(forced, BaseException) and bool(_value(answer).get("seen"))


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
            where = params | {"executionContextId": context}
            resolved = await send_on_handle(session, "DOM.resolveNode", where)
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
