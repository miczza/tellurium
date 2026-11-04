// `this` is a link, or with `frame` the <iframe> that holds one: then only whether a
// person could see and reach what it shows is checked. `framed`: in a frame itself.
function (frame) {
    const el = this, doc = el.ownerDocument, win = doc.defaultView;
    const MIN = 2, SAME = 3, CAP = 200, FAINT = 0.05;
    const css = (n, pseudo) => win.getComputedStyle(n, pseudo);
    const up = (n) => n.assignedSlot || n.parentElement || n.getRootNode().host || null;
    const chain = [];
    for (let n = el; n; n = up(n)) chain.push(n);
    const out = [];
    if (chain.some((n) => n.getAttribute('aria-hidden') === 'true')) out.push('aria-hidden');
    if (chain.some((n) => n.hasAttribute('inert'))) out.push('inert');
    const marker = /honey[-_]?pot/i;
    if (!frame && ['id', 'class', 'name'].some((a) => marker.test(el.getAttribute(a) || ''))) {
        out.push('honeypot-marker');
    }
    const nofollow = !frame && /(^|\s)nofollow(\s|$)/i.test(el.getAttribute('rel') || '');
    const finish = (list = out) => ({
        reasons: list.length && nofollow ? [...list, 'nofollow'] : list, nofollow, framed: win.parent !== win,
    });
    const shown = el.checkVisibility ? el.checkVisibility() : true;
    if (!shown || el.getClientRects().length === 0) {
        out.push('not-rendered');
        return finish();
    }
    const own = css(el);
    if (own.visibility !== 'visible') out.push('visibility-hidden');
    // How much of the link shows through its own and its ancestors' opacity.
    const computed = (n, prop) => css(n).getPropertyValue(prop);
    const rgba = (c) => {
        const p = ((/^rgba?\(([^)]*)\)$/.exec(c || '') || [])[1] || '').split(/[\s,\/]+/).filter(Boolean).map(Number);
        return p.length < 3 || p.some(isNaN) ? null : [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
    };
    const clear = (mask) => clearMask(mask || 'none');
    const fade = (n, value) => {
        let shows = parseFloat(value(n, 'opacity'));
        for (const [, x, pct] of (value(n, 'filter') || '').matchAll(/opacity\(\s*([\d.]+)(%?)\s*\)/g)) {
            shows *= Math.min(pct ? x / 100 : +x, 1);
        }
        return clear(value(n, 'mask-image')) || clear(value(n, '-webkit-mask-image')) ? 0 : shows;
    };
    const seenThrough = (value) => chain.reduce((p, n) => p * fade(n, value), 1);
    if (seenThrough(computed) < FAINT) out.push('transparent');  // under 5% all told
    if (own.pointerEvents === 'none') out.push('no-pointer');

    const rect = (r) => ({l: r.left, t: r.top, r: r.right, b: r.bottom});
    const small = (a) => a.r - a.l < MIN || a.b - a.t < MIN;
    const meet = (a, b) => ({
        l: Math.max(a.l, b.l), t: Math.max(a.t, b.t), r: Math.min(a.r, b.r), b: Math.min(a.b, b.b),
    });
    const clips = (v) => v === 'hidden' || v === 'clip';
    const paints = (s) => /\b(paint|strict|content)\b/.test(s.contain || '');  // cuts like overflow: clip
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
    const cuts = [];  // [box, how] of each box that cut part of the link away
    const cutBy = (n, how, before, after) => {
        if (['l', 't', 'r', 'b'].some((k) => after[k] !== before[k])) cuts.push([n, how]);
        return after;
    };
    const shape = (n, s, vis) => {
        const r = n.getBoundingClientRect();
        if (s.clip && s.clip.startsWith('rect(') && (s.position === 'absolute' || s.position === 'fixed')) {
            const [t, rr, b, l] = s.clip.slice(5, -1).split(/[\s,]+/);
            const at = (v, auto) => (v === 'auto' ? auto : parseFloat(v));
            vis = cutBy(n, 'clip', vis, meet(vis, {
                l: r.left + at(l, 0), t: r.top + at(t, 0),
                r: r.left + at(rr, r.width), b: r.top + at(b, r.height),
            }));
        }
        const cut = clipShape(s.clipPath || 'none', r);
        return cut ? cutBy(n, 'clip-path', vis, meet(vis, cut)) : vis;
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
    const offAxes = new Set();  // 'l' (across) and 't' (down): along which it is off the page
    const shift = {l: 0, t: 0};
    const hold = (n, s) => {
        const r = n.getBoundingClientRect(), l = r.left + n.clientLeft, t = r.top + n.clientTop;
        const pad = {l, t, r: l + n.clientWidth, b: t + n.clientHeight};
        const x = s.direction === 'rtl' ? pad.r - n.scrollLeft - n.scrollWidth : l - n.scrollLeft;
        const span = {l: x, t: t - n.scrollTop, r: x + n.scrollWidth, b: t - n.scrollTop + n.scrollHeight};
        for (const [axis, lo, hi] of axes) {
            const scrolled = scrolls(s[axis]);
            if (!scrolled && !clips(s[axis]) && !paints(s)) continue;
            const how = clips(s[axis]) || scrolled ? 'overflow' : 'contain';
            const room = scrolled ? span : pad;
            if (vis[hi] <= room[lo] || vis[lo] >= room[hi]) {
                if (scrolled || n === body) {  // the page itself does not scroll there
                    off = true;
                    offAxes.add(lo);
                } else cuts.push([n, how]);
                vis[hi] = vis[lo];
                continue;
            }
            const inside = Math.min(vis[hi], pad[hi]) - Math.max(vis[lo], pad[lo]);
            if (!scrolled || inside >= MIN) {
                if (!scrolled && (vis[lo] < pad[lo] || vis[hi] > pad[hi])) cuts.push([n, how]);
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
    for (let n = up(el); n && !off && !small(vis); n = up(n)) {
        const s = css(n);
        if (s.display === 'contents') continue;
        // a positioned box, or one that contains paint, holds an absolute link; only the
        // latter holds a fixed one
        if ((abs && s.position === 'static' && !paints(s)) || (fixed && !paints(s))) continue;
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
    if (!off && !small(vis)) {
        if (vis.r <= x0 || vis.l >= x1) offAxes.add('l');
        if (vis.b <= y0 || vis.t >= y1) offAxes.add('t');
        off = offAxes.size > 0;
    }
    let geometry = null;
    if (small(area)) geometry = 'zero-size';
    else if (off) geometry = 'off-page';
    else if (small(vis)) geometry = 'clipped';

    // Hidden until a person tabs to it, as a "skip to content" link: not a trap.
    const hidden = geometry || out.includes('transparent');
    if (hidden && !frame && reveals(geometry)) return finish(out.filter((signal) => signal !== 'transparent'));
    if (geometry) out.push(geometry);
    if (geometry || out.includes('visibility-hidden') || out.includes('transparent')) {
        return finish();  // nothing of it to see: what it holds does not matter
    }
    if (!out.includes('no-pointer') && covered()) {
        out.push('covered');
        return finish();
    }
    if (frame) return finish();  // what the frame shows is the link's own check

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

    // Hit-tested where it shows in the viewport, as a click would be: covered when no
    // point lands on it or inside it. Not where it would take a scroll to be seen, so a
    // fixed or sticky box (a header, a cookie banner) over a link that is not pinned
    // itself does not count: scrolling takes the link out from under it.
    function pinned(n) {
        for (; n && n.nodeType === 1; n = n.parentElement || n.getRootNode().host) {
            const p = win.getComputedStyle(n).position;
            if (p === 'fixed' || p === 'sticky') return true;
        }
        return false;
    }
    function covered() {
        if (shift.l || shift.t) return false;
        const at = el.getRootNode().elementFromPoint ? el.getRootNode() : doc;
        const view = meet(vis, {l: 0, t: 0, r: win.innerWidth, b: win.innerHeight});
        range.selectNodeContents(el);
        const points = [];
        for (const r of [...el.getClientRects(), ...range.getClientRects()].slice(0, 20)) {
            const b = meet(rect(r), view);
            if (small(b)) continue;
            for (const [x, y] of [[0.5, 0.5], [0.25, 0.25], [0.75, 0.25], [0.25, 0.75], [0.75, 0.75]]) {
                points.push([b.l + x * (b.r - b.l), b.t + y * (b.b - b.t)]);
            }
        }
        const scrolls = !pinned(el);
        let blocked = 0;
        for (const [x, y] of points) {
            const hit = at.elementFromPoint(x, y);
            if (hit && (hit === el || el.contains(hit))) return false;
            if (!(hit && scrolls && pinned(hit))) blocked++;
        }
        return blocked > 0;
    }
{{STYLE}}
}
