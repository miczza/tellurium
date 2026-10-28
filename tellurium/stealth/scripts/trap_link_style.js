    // The style checks of trap_link.js (focus rules, CSS lengths). Not valid JS on its
    // own: trap_link.py pastes it, as text, at the {{STYLE}} placeholder near the end of
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
    // nesting followed). An inline style beats a rule that is not !important; a sheet that
    // cannot be read (cross-origin) brings nothing back.
    function focusRules() {
        const found = new Map();
        let budget = 10000;
        const kind = (rule) => Object.prototype.toString.call(rule).slice(8, -1);
        const parts = (list) => {  // a selector list split at its top-level commas
            const out = [];
            let depth = 0, from = 0;
            for (let i = 0; i < list.length; i++) {
                const c = list[i];
                if (c === '(' || c === '[') depth++;
                else if (c === ')' || c === ']') depth--;
                else if (c === ',' && !depth) { out.push(list.slice(from, i)); from = i + 1; }
            }
            return [...out, list.slice(from)].map((part) => part.trim()).filter(Boolean);
        };
        const compose = (outer, inner) => parts(inner).map((part) => (
            part.includes('&') ? part.replace(/&/g, `:is(${outer})`) : `:is(${outer}) ${part}`
        )).join(', ');
        const put = (n, style) => {
            const mine = found.get(n) || new Map();
            for (const prop of style) {
                const strong = style.getPropertyPriority(prop) === 'important';
                if (n.style && n.style.getPropertyValue(prop)
                    && (!strong || n.style.getPropertyPriority(prop) === 'important')) continue;
                if (mine.has(prop) && mine.get(prop).strong && !strong) continue;
                mine.set(prop, {value: style.getPropertyValue(prop).trim(), strong});
            }
            if (mine.size) found.set(n, mine);
        };
        const apply = (selector, style) => {
            for (const part of parts(selector)) {
                if (!part.includes(':focus')) continue;
                for (const n of chain) {
                    let sel = part.replace(/:focus-within(?![\w-])/g, '');
                    if (/:focus(-visible)?(?![\w-])/.test(sel)) {
                        if (n !== el) continue;  // only the link itself takes the focus
                        sel = sel.replace(/:focus(-visible)?(?![\w-])/g, ':scope');
                    }
                    let hit = false;
                    try { hit = n.matches(sel.trim() || '*'); } catch (e) { /* matches() cannot take it */ }
                    if (hit) put(n, style);
                }
            }
        };
        const fits = (media) => !media || !media.mediaText || win.matchMedia(media.mediaText).matches;
        const read = (sheet, outer) => {
            if (!sheet || sheet.disabled || !fits(sheet.media)) return;
            let list;
            try { list = sheet.cssRules; } catch (e) { return; }  // cross-origin: nothing presumed
            if (list) scan(list, outer);
        };
        const scan = (list, outer) => {
            for (const rule of list) {
                if (--budget < 0) return;
                const type = kind(rule);
                if (type === 'CSSStyleRule') {
                    const selector = outer ? compose(outer, rule.selectorText) : rule.selectorText;
                    apply(selector, rule.style);
                    if (rule.cssRules && rule.cssRules.length) scan(rule.cssRules, selector);
                } else if (type === 'CSSNestedDeclarations') {
                    if (outer) apply(outer, rule.style);
                } else if (type === 'CSSImportRule') {
                    if (fits(rule.media)) read(rule.styleSheet, outer);
                } else if (type === 'CSSMediaRule') {
                    if (fits(rule.media)) scan(rule.cssRules, outer);
                } else if (type === 'CSSSupportsRule') {
                    if (win.CSS.supports(rule.conditionText)) scan(rule.cssRules, outer);
                } else if (type === 'CSSLayerBlockRule') {
                    scan(rule.cssRules, outer);
                }  // @container, @scope and the like: what they hold is not presumed to apply
            }
        };
        const root = el.getRootNode();
        const sheets = [...doc.styleSheets, ...(doc.adoptedStyleSheets || [])];
        if (root !== doc) sheets.push(...(root.styleSheets || []), ...(root.adoptedStyleSheets || []));
        for (const sheet of sheets) read(sheet, '');
        return budget < 0 ? new Map() : found;  // too many rules to read through: nothing presumed
    }
