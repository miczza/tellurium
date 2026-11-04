    // The style checks of trap_link.js (focus rules, CSS lengths, masks). Not valid JS on
    // its own: trap_link.py pastes it, as text, at the STYLE placeholder near the end of
    // the function in trap_link.js, whose variables (el, css, chain, ...) it uses.
    // Guarded by tests/unit/test_trap_link.py::
    // test_the_check_is_the_script_shipped_with_the_stealth_scripts.
    // Whether the values the :focus, :focus-visible and :focus-within rules declare
    // undo what hides the link, once a person tabs to it. They are read, never applied:
    // nothing is fetched, no transition starts, the focus does not move.
    function reveals(geometry) {
        if (el.tabIndex < 0) return false;  // out of the tab order: never focused
        const rules = focusRules();
        if (!rules.size) return false;
        const declared = (n, prop) => {
            const mine = rules.get(n);
            return mine && mine.has(prop) ? mine.get(prop).value : null;
        };
        const value = (n, prop) => declared(n, prop) ?? computed(n, prop);
        if (seenThrough(value) <= 0) return false;
        const lifted = (n, how) => {
            const s = css(n);
            if (how === 'clip') {
                const applies = s.clip.startsWith('rect(') && ['absolute', 'fixed'].includes(s.position);
                return !applies || declared(n, 'clip') === 'auto'
                    || ['static', 'relative', 'sticky'].includes(declared(n, 'position'));
            }
            if (how === 'clip-path') return s.clipPath === 'none' || declared(n, 'clip-path') === 'none';
            if (how === 'contain') return declared(n, 'contain') === 'none';
            return ['overflow-x', 'overflow-y'].every((prop) => declared(n, prop) === 'visible');
        };
        if (geometry === 'clipped') return cuts.every(([n, how]) => lifted(n, how));
        if (geometry === 'zero-size') {
            if (!lifted(el, 'clip') || !lifted(el, 'clip-path')) return false;
            if (parseFloat(own.fontSize) < 1) return size(el, declared(el, 'font-size'), 16) >= 1;
            const fits = (props, whole) => props.some((prop) => {
                const v = declared(el, prop);
                return v === 'auto' || size(el, v, whole) >= MIN;
            });
            const parent = el.offsetParent || html;
            return (area.r - area.l >= MIN || fits(['width', 'min-width'], parent.clientWidth))
                && (area.b - area.t >= MIN || fits(['height', 'min-height'], parent.clientHeight));
        }
        if (geometry !== 'off-page') return true;
        // Off the page: where the declared offsets move it to, along each axis it is off.
        const sides = {l: [['left', 1], ['right', -1]], t: [['top', 1], ['bottom', -1]]};
        const moved = {...area};
        for (const axis of offAxes) {
            let back = false;
            for (const n of chain) {
                const s = css(n), position = declared(n, 'position') ?? s.position;
                if (position === 'static') {
                    if (s.position === 'static') continue;
                    back = 'flow';  // back to its place in the flow
                    break;
                }
                const whole = axis === 'l' ? (n.offsetParent || html).clientWidth : (n.offsetParent || html).clientHeight;
                const [prop, sign] = sides[axis].find(([side]) => declared(n, side) !== null) || [];
                const to = prop ? size(n, declared(n, prop), whole) : NaN, from = prop ? parseFloat(s[prop]) : NaN;
                if (isNaN(to) || isNaN(from)) continue;
                const far = axis === 'l' ? 'r' : 'b';
                moved[axis] += sign * (to - from);
                moved[far] += sign * (to - from);
                back = true;
            }
            if (!back) return false;
            if (back === 'flow') continue;
            const [lo, hi] = axis === 'l' ? [x0, x1] : [y0, y1];
            if (moved[axis === 'l' ? 'r' : 'b'] <= lo || moved[axis] >= hi) return false;
        }
        return true;
    }
    // Whether a mask-image hides the whole box: gradients only, every color of them
    // transparent. A color whose alpha cannot be told (a named one, currentcolor,
    // color-mix() or var() in a declared value), a url() or an image-set() may show.
    function clearMask(mask) {
        const layers = splitTop(mask.trim());
        if (!layers.some((layer) => /gradient\(/.test(layer))) return false;
        const KEYWORDS = new Set(['to', 'left', 'right', 'top', 'bottom', 'center', 'at',
            'from', 'in', 'circle', 'ellipse', 'closest-side', 'closest-corner', 'farthest-side',
            'farthest-corner', 'shorter', 'longer', 'increasing', 'decreasing', 'hue', 'srgb',
            'srgb-linear', 'display-p3', 'a98-rgb', 'prophoto-rgb', 'rec2020', 'lab', 'oklab',
            'xyz', 'xyz-d50', 'xyz-d65', 'hsl', 'hwb', 'lch', 'oklch']);
        const TOKEN = /[a-z-]+\((?:[^()]|\([^()]*\))*\)|#[0-9a-f]+|-?[\d.][\w.%]*|-?[a-z_][\w-]*/gi;
        let colors = 0;
        for (const layer of layers) {
            if (layer === 'none') continue;  // a layer with no image: transparent
            const g = /^(?:repeating-)?(?:linear|radial|conic)-gradient\((.*)\)$/i.exec(layer);
            if (!g) return false;
            for (const token of g[1].match(TOKEN) || []) {
                const fn = /^([a-z-]+)\(/i.exec(token);
                const name = (fn ? fn[1] : token).toLowerCase();
                if (fn && ['calc', 'min', 'max', 'clamp'].includes(name)) continue;  // a stop
                if (!fn && (/^-?[\d.]/.test(token) || KEYWORDS.has(name))) continue;
                colors++;
                if (alpha(token) !== 0) return false;
            }
        }
        return colors > 0;
    }
    // The alpha of a CSS color: transparent, #hex, rgb(), hsl() and the forms with
    // "/ alpha" (lab, lch, oklab, oklch, color, hwb); NaN when it cannot be told.
    function alpha(c) {
        c = c.trim().toLowerCase();
        if (c === 'transparent') return 0;
        const hex = /^#([0-9a-f]+)$/.exec(c);
        if (hex) {
            const h = hex[1];
            if (h.length === 4) return parseInt(h[3], 16) / 15;
            if (h.length === 8) return parseInt(h.slice(6), 16) / 255;
            return h.length === 3 || h.length === 6 ? 1 : NaN;
        }
        const m = /^(rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(([^()]*)\)$/.exec(c);
        if (!m) return NaN;
        const args = m[2];
        let a = null;
        if (args.includes('/')) a = args.slice(args.lastIndexOf('/') + 1);
        else if (args.includes(',') && /^(rgb|hsl)a?$/.test(m[1])) a = args.split(',')[3] ?? null;
        if (a === null) return 1;
        a = a.trim();
        if (a === 'none') return 0;
        const x = parseFloat(a);
        return a.endsWith('%') ? x / 100 : x;
    }
    // A comma-separated list split at its top-level commas.
    function splitTop(list) {
        const out = [];
        let depth = 0, from = 0;
        for (let i = 0; i < list.length; i++) {
            const c = list[i];
            if (c === '(' || c === '[') depth++;
            else if (c === ')' || c === ']') depth--;
            else if (c === ',' && !depth) { out.push(list.slice(from, i)); from = i + 1; }
        }
        return [...out, list.slice(from)].map((part) => part.trim()).filter(Boolean);
    }
    // A declared length in CSS px (NaN when it cannot be told: calc(), auto, ...).
    function size(n, v, whole) {
        const m = /^(-?[\d.]+(?:e-?\d+)?)(px|%|em|rem|vw|vh)?$/.exec((v || '').trim());
        if (!m) return NaN;
        const x = parseFloat(m[1]), unit = m[2];
        if (unit === '%') return (x / 100) * whole;
        if (unit === 'em') return x * parseFloat(css(n.parentElement || n).fontSize);
        if (unit === 'rem') return x * parseFloat(css(html).fontSize);
        if (unit === 'vw' || unit === 'vh') return (x / 100) * (unit === 'vw' ? win.innerWidth : win.innerHeight);
        return unit === 'px' || x === 0 ? x : NaN;
    }
    // node -> (property -> value) the focus rules of the readable sheets would set on the
    // link and its ancestors, once it has the focus (@import, @media, @supports, @layer and
    // nesting followed): only a value that wins the cascade there, by importance, layer,
    // specificity and order, against every rule of those sheets that matches the node now
    // (an inline style beats a rule that is not !important). A sheet that cannot be read
    // (cross-origin) brings nothing back. Layers are ranked in the order they are first
    // met, a nested one as a layer of its own.
    function focusRules() {
        const found = new Map();
        const others = [];  // the rules that do not need the focus: {part, style, rank}
        const layers = new Map();
        let budget = 10000, order = 0, anonymous = 0;
        const kind = (rule) => Object.prototype.toString.call(rule).slice(8, -1);
        const parts = splitTop;  // a selector list split at its top-level commas
        const compose = (outer, inner) => parts(inner).map((part) => (
            part.includes('&') ? part.replace(/&/g, `:is(${outer})`) : `:is(${outer}) ${part}`
        )).join(', ');
        const layer = (outer, name) => {
            const full = outer === null ? name : `${outer}.${name}`;
            if (!layers.has(full)) layers.set(full, layers.size);
            return full;
        };
        const key = (style, prop, rank) => ({...rank, strong: style.getPropertyPriority(prop) === 'important'});
        const beats = (a, b) => {
            if (a.strong !== b.strong) return a.strong;
            const la = a.layer === null ? Infinity : layers.get(a.layer);
            const lb = b.layer === null ? Infinity : layers.get(b.layer);
            if (la !== lb) return a.strong ? la < lb : la > lb;
            for (let k = 0; k < 3; k++) if (a.spec[k] !== b.spec[k]) return a.spec[k] > b.spec[k];
            return a.order > b.order;
        };
        const put = (n, style, rank) => {
            const mine = found.get(n) || new Map();
            for (const prop of style) {
                const mark = key(style, prop, rank);
                if (n.style && n.style.getPropertyValue(prop)
                    && (!mark.strong || n.style.getPropertyPriority(prop) === 'important')) continue;
                if (mine.has(prop) && !beats(mark, mine.get(prop).mark)) continue;
                mine.set(prop, {value: style.getPropertyValue(prop).trim(), mark});
            }
            if (mine.size) found.set(n, mine);
        };
        const apply = (selector, style, within) => {
            order++;
            for (const part of parts(selector)) {
                const rank = {layer: within, spec: specificity(part), order};
                if (!part.includes(':focus')) {
                    others.push({part, style, rank});
                    continue;
                }
                for (const n of chain) {
                    let sel = part.replace(/:focus-within(?![\w-])/g, '');
                    if (/:focus(-visible)?(?![\w-])/.test(sel)) {
                        if (n !== el) continue;  // only the link itself takes the focus
                        sel = sel.replace(/:focus(-visible)?(?![\w-])/g, ':scope');
                    }
                    let hit = false;
                    try { hit = n.matches(sel.trim() || '*'); } catch (e) { /* matches() cannot take it */ }
                    if (hit) put(n, style, rank);
                }
            }
        };
        const fits = (media) => !media || !media.mediaText || win.matchMedia(media.mediaText).matches;
        const read = (sheet, outer, within) => {
            if (!sheet || sheet.disabled || !fits(sheet.media)) return;
            let list;
            try { list = sheet.cssRules; } catch (e) { return; }  // cross-origin: nothing presumed
            if (list) scan(list, outer, within);
        };
        const scan = (list, outer, within) => {
            for (const rule of list) {
                if (--budget < 0) return;
                const type = kind(rule);
                if (type === 'CSSStyleRule') {
                    const selector = outer ? compose(outer, rule.selectorText) : rule.selectorText;
                    apply(selector, rule.style, within);
                    if (rule.cssRules && rule.cssRules.length) scan(rule.cssRules, selector, within);
                } else if (type === 'CSSNestedDeclarations') {
                    if (outer) apply(outer, rule.style, within);
                } else if (type === 'CSSImportRule') {
                    const named = rule.layerName;
                    const into = named === null || named === undefined ? within
                        : layer(within, named || `#${anonymous++}`);
                    if (fits(rule.media)) read(rule.styleSheet, outer, into);
                } else if (type === 'CSSMediaRule') {
                    if (fits(rule.media)) scan(rule.cssRules, outer, within);
                } else if (type === 'CSSSupportsRule') {
                    if (win.CSS.supports(rule.conditionText)) scan(rule.cssRules, outer, within);
                } else if (type === 'CSSLayerBlockRule') {
                    scan(rule.cssRules, outer, layer(within, rule.name || `#${anonymous++}`));
                } else if (type === 'CSSLayerStatementRule') {
                    for (const name of rule.nameList) layer(within, name);
                }  // @container, @scope and the like: what they hold is not presumed to apply
            }
        };
        const root = el.getRootNode();
        const sheets = [...doc.styleSheets, ...(doc.adoptedStyleSheets || [])];
        if (root !== doc) sheets.push(...(root.styleSheets || []), ...(root.adoptedStyleSheets || []));
        for (const sheet of sheets) read(sheet, '', null);
        if (budget < 0) return new Map();  // too many rules to read through: nothing presumed
        // A focus value only counts if no rule that applies already outranks it there.
        for (const [n, mine] of found) {
            for (const [prop, {mark}] of mine) {
                for (const other of others) {
                    if (!other.style.getPropertyValue(prop)) continue;
                    if (!beats(key(other.style, prop, other.rank), mark)) continue;
                    let hit = false;
                    try { hit = n.matches(other.part); } catch (e) { /* matches() cannot take it */ }
                    if (hit) { mine.delete(prop); break; }
                }
            }
            if (!mine.size) found.delete(n);
        }
        return found;
    }
    // [ids, classes / attributes / pseudo-classes, types / pseudo-elements] of a complex
    // selector: :is(), :not() and :has() count their most specific argument, :where() none.
    function specificity(sel) {
        const s = [0, 0, 0];
        const ident = /^-?(?:[\w-]|\\.|[^\x00-\x7f])+/;
        const name = (at) => (ident.exec(sel.slice(at)) || [''])[0];
        const closing = (at) => {  // the index of the bracket closing the one at *at*
            const open = sel[at], shut = open === '(' ? ')' : ']';
            let depth = 0;
            for (let k = at; k < sel.length; k++) {
                if (sel[k] === '\\') k++;
                else if (sel[k] === '"' || sel[k] === "'") {
                    const end = sel.indexOf(sel[k], k + 1);  // a string: skipped whole
                    k = end < 0 ? sel.length : end;
                }
                else if (sel[k] === open) depth++;
                else if (sel[k] === shut && !--depth) return k;
            }
            return sel.length;
        };
        const most = (list) => splitTop(list).map(specificity).reduce((m, t) => (
            t[0] - m[0] || t[1] - m[1] || t[2] - m[2]) > 0 ? t : m, [0, 0, 0]);
        const add = (t) => { for (let k = 0; k < 3; k++) s[k] += t[k]; };
        let i = 0;
        while (i < sel.length) {
            const c = sel[i];
            if (c === '#' || c === '.') {
                s[c === '#' ? 0 : 1]++;
                i += 1 + name(i + 1).length;
            } else if (c === '[') {
                s[1]++;
                i = closing(i) + 1;
            } else if (c === ':') {
                const element = sel[i + 1] === ':';
                const start = i + (element ? 2 : 1), pseudo = name(start).toLowerCase();
                let j = start + pseudo.length, args = null;
                if (sel[j] === '(') {
                    const end = closing(j);
                    args = sel.slice(j + 1, end);
                    j = end + 1;
                }
                const of = args === null ? -1 : args.search(/\sof\s/i);
                if (element || ['before', 'after', 'first-line', 'first-letter'].includes(pseudo)) s[2]++;
                else if (['is', 'not', 'has', 'matches', '-webkit-any'].includes(pseudo)) add(most(args || ''));
                else if (pseudo === 'where') { /* nothing */ }
                else if (/^nth-(last-)?child$/.test(pseudo) && of >= 0) { s[1]++; add(most(args.slice(of + 4))); }
                else s[1]++;
                i = j;
            } else if (/[a-z_\-\u0080-￿\\]/i.test(c)) {
                s[2]++;  // a type selector
                i += Math.max(name(i).length, 1);
            } else {
                i++;  // a combinator, *, a namespace bar
            }
        }
        return s;
    }
