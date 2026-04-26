"""T7.6 F2: adversarial invariants of the runtime webdriver/toString mask.

These tests are not new features — they pin invariants that the P3
implementation (commit c4932ec) already satisfies. Their value is
regression coverage for refactors and for plausible upstream evolution
of the CreepJS classifiers (see lies/index.ts in the CreepJS repo).
"""
from __future__ import annotations
import os
import shutil

import pytest

from tellurium import Browser

pytestmark = pytest.mark.stealth

STOCK_CHROME = os.environ.get("STOCK_CHROME", "/usr/bin/google-chrome-stable")

_skip_no_chrome = pytest.mark.skipif(
    not shutil.which(STOCK_CHROME) and not os.path.exists(STOCK_CHROME),
    reason="Stock Chrome not installed",
)


@_skip_no_chrome
async def test_webdriver_value_is_false():
    """#1 — navigator.webdriver MUST evaluate falsy in stealth mode."""
    async with await Browser.launch(headless=True, stealth=True) as browser:
        tab = await browser.new_tab("about:blank")
        result = await tab.eval("navigator.webdriver")
        assert result is None or result is False


@_skip_no_chrome
async def test_webdriver_getter_shape():
    """#2 — getter has name='get webdriver', no .prototype, non-constructable."""
    async with await Browser.launch(headless=True, stealth=True) as browser:
        tab = await browser.new_tab("about:blank")
        result = await tab.eval("""
            (() => {
              const g = Object.getOwnPropertyDescriptor(
                Object.getPrototypeOf(navigator), 'webdriver').get;
              let constructable = true;
              try { new g(); } catch (e) { constructable = false; }
              return {
                name: g.name,
                hasPrototype: 'prototype' in g,
                constructable,
              };
            })()
        """)
        assert result == {
            "name": "get webdriver",
            "hasPrototype": False,
            "constructable": False,
        }


@_skip_no_chrome
async def test_webdriver_toString_call():
    """#3 — Function.prototype.toString.call(getter) returns native shape."""
    async with await Browser.launch(headless=True, stealth=True) as browser:
        tab = await browser.new_tab("about:blank")
        result = await tab.eval("""
            (() => {
              const g = Object.getOwnPropertyDescriptor(
                Object.getPrototypeOf(navigator), 'webdriver').get;
              return Function.prototype.toString.call(g);
            })()
        """)
        assert result == "function get webdriver() { [native code] }"


@_skip_no_chrome
async def test_webdriver_toString_bind():
    """#4 — Function.prototype.toString.bind(getter)() returns native shape."""
    async with await Browser.launch(headless=True, stealth=True) as browser:
        tab = await browser.new_tab("about:blank")
        result = await tab.eval("""
            (() => {
              const g = Object.getOwnPropertyDescriptor(
                Object.getPrototypeOf(navigator), 'webdriver').get;
              return Function.prototype.toString.bind(g)();
            })()
        """)
        assert result == "function get webdriver() { [native code] }"


@_skip_no_chrome
async def test_webdriver_toString_reflect_apply():
    """#5 — Reflect.apply(Function.prototype.toString, getter, []) returns native shape."""
    async with await Browser.launch(headless=True, stealth=True) as browser:
        tab = await browser.new_tab("about:blank")
        result = await tab.eval("""
            (() => {
              const g = Object.getOwnPropertyDescriptor(
                Object.getPrototypeOf(navigator), 'webdriver').get;
              return Reflect.apply(Function.prototype.toString, g, []);
            })()
        """)
        assert result == "function get webdriver() { [native code] }"


@_skip_no_chrome
async def test_webdriver_getter_wrong_this_throws():
    """#6 — getter.call({}) throws TypeError (Illegal invocation invariant)."""
    async with await Browser.launch(headless=True, stealth=True) as browser:
        tab = await browser.new_tab("about:blank")
        result = await tab.eval("""
            (() => {
              const g = Object.getOwnPropertyDescriptor(
                Object.getPrototypeOf(navigator), 'webdriver').get;
              try { g.call({}); return null; }
              catch (e) { return e.constructor.name; }
            })()
        """)
        assert result == "TypeError"


@_skip_no_chrome
async def test_fakeToString_self_shape():
    """#7 — Function.prototype.toString.call(Function.prototype.toString) is native."""
    async with await Browser.launch(headless=True, stealth=True) as browser:
        tab = await browser.new_tab("about:blank")
        result = await tab.eval("""
            Function.prototype.toString.call(Function.prototype.toString)
        """)
        assert result == "function toString() { [native code] }"


@_skip_no_chrome
async def test_fakeToString_no_prototype():
    """#8 — Function.prototype.toString has no .prototype (non-constructable shape)."""
    async with await Browser.launch(headless=True, stealth=True) as browser:
        tab = await browser.new_tab("about:blank")
        result = await tab.eval("'prototype' in Function.prototype.toString")
        assert result is False


@_skip_no_chrome
async def test_fakeToString_descriptor_shape():
    """#9 — descriptor of Function.prototype.toString matches native shape."""
    async with await Browser.launch(headless=True, stealth=True) as browser:
        tab = await browser.new_tab("about:blank")
        result = await tab.eval("""
            (() => {
              const d = Object.getOwnPropertyDescriptor(
                Function.prototype, 'toString');
              return {
                hasValue: 'value' in d,
                writable: d.writable,
                enumerable: d.enumerable,
                configurable: d.configurable,
              };
            })()
        """)
        assert result == {
            "hasValue": True,
            "writable": True,
            "enumerable": False,
            "configurable": True,
        }


@_skip_no_chrome
async def test_chrome_runtime_stubs_have_no_prototype():
    """#12 — 'prototype' in chrome.runtime.sendMessage is false (T7.5 P3 guard)."""
    async with await Browser.launch(headless=True, stealth=True) as browser:
        tab = await browser.new_tab("about:blank")
        result = await tab.eval("""
            (() => {
              const r = window.chrome && window.chrome.runtime;
              if (!r) return null;
              return {
                connect: 'prototype' in r.connect,
                sendMessage: 'prototype' in r.sendMessage,
              };
            })()
        """)
        assert result == {"connect": False, "sendMessage": False}


@_skip_no_chrome
async def test_oopif_webdriver_native_shape():
    """#14 — inside a pre-existing iframe (via initial HTML): webdriver=false and getter toString native.

    Stealth injection propagates to iframes that are part of the initial document
    load (via data: URL with an inline <iframe> element), but does NOT propagate to
    iframes dynamically appended after the page loads (src='about:blank').  The
    pre-existing-iframe path exercises the same cross-realm invariant without
    depending on dynamic injection.
    """
    async with await Browser.launch(headless=True, stealth=True) as browser:
        # Navigate to a page that already has an iframe in its initial HTML.
        tab = await browser.new_tab("data:text/html,<html><body><iframe id=t></iframe></body></html>")
        result = await tab.eval("""
            (async () => {
              const iframe = document.getElementById('t');
              // Small settle wait in case contentWindow realm isn't ready yet.
              await new Promise(r => setTimeout(r, 100));
              const w = iframe.contentWindow;
              const g = Object.getOwnPropertyDescriptor(
                Object.getPrototypeOf(w.navigator), 'webdriver').get;
              return {
                value: w.navigator.webdriver,
                getterToString: w.Function.prototype.toString.call(g),
              };
            })()
        """)
        assert result["value"] in (False, None)
        assert result["getterToString"] == "function get webdriver() { [native code] }"


@_skip_no_chrome
async def test_object_prototype_toString_class_slot():
    """#16 — Object.prototype.toString.call(getter) === '[object Function]'.

    Exercises the [[Class]] internal slot via the alternative path
    (Object.prototype.toString rather than Function.prototype.toString).
    Used by CreepJS 'Object toString error' check.
    """
    async with await Browser.launch(headless=True, stealth=True) as browser:
        tab = await browser.new_tab("about:blank")
        result = await tab.eval("""
            (() => {
              const g = Object.getOwnPropertyDescriptor(
                Object.getPrototypeOf(navigator), 'webdriver').get;
              return Object.prototype.toString.call(g);
            })()
        """)
        assert result == "[object Function]"


@_skip_no_chrome
async def test_reflect_ownKeys_getter():
    """#17 — Reflect.ownKeys(getter) === ['length','name'].

    Generalises #2 (Object.getOwnPropertyNames) to the Reflect path,
    which CreepJS uses explicitly.
    """
    async with await Browser.launch(headless=True, stealth=True) as browser:
        tab = await browser.new_tab("about:blank")
        result = await tab.eval("""
            (() => {
              const g = Object.getOwnPropertyDescriptor(
                Object.getPrototypeOf(navigator), 'webdriver').get;
              return Reflect.ownKeys(g).sort().join(',');
            })()
        """)
        assert result == "length,name"


@_skip_no_chrome
async def test_class_extends_getter_throws():
    """#18 — class X extends getter {} throws TypeError ([[Construct]] invariant).

    Distinct from `new getter()` because class-extends operates through a
    different branch of the constructor semantics. Used by CreepJS
    'Class extends error' check.
    """
    async with await Browser.launch(headless=True, stealth=True) as browser:
        tab = await browser.new_tab("about:blank")
        result = await tab.eval("""
            (() => {
              const g = Object.getOwnPropertyDescriptor(
                Object.getPrototypeOf(navigator), 'webdriver').get;
              try { eval('class X extends g {}'); return null; }
              catch (e) { return e.constructor.name; }
            })()
        """)
        assert result == "TypeError"


@_skip_no_chrome
async def test_webdriver_descriptor_shape():
    """#19 — descriptor on Navigator.prototype.webdriver matches native shape.

    Pins the descriptor that CreepJS uses to *discover* the getter before
    running queryLies on it.

    Implementation note: the assertion uses `setIsUndefined: bool` rather
    than `set: d.set` because CDP's Runtime.evaluate JSON-serialises the
    return value, and `undefined` keys are dropped from the resulting
    object. A boolean preserves the semantic invariant ("descriptor has
    no setter") while surviving the serialisation boundary.
    """
    async with await Browser.launch(headless=True, stealth=True) as browser:
        tab = await browser.new_tab("about:blank")
        result = await tab.eval("""
            (() => {
              const proto = Object.getPrototypeOf(navigator);
              const d = Object.getOwnPropertyDescriptor(proto, 'webdriver');
              return {
                hasGet: typeof d.get === 'function',
                setIsUndefined: d.set === undefined,
                enumerable: d.enumerable,
                configurable: d.configurable,
                getMatchesPath: Function.prototype.toString.call(d.get) ===
                  'function get webdriver() { [native code] }',
              };
            })()
        """)
        assert result == {
            "hasGet": True,
            "setIsUndefined": True,
            "enumerable": True,
            "configurable": True,
            "getMatchesPath": True,
        }


@_skip_no_chrome
async def test_chrome_runtime_sendMessage_native_shape():
    """#10 — chrome.runtime.sendMessage.toString() returns native shape.

    Closes the F1 leak: stub previously returned "() => {...}" which would
    fire any classifier that checks the trailing `[native code] }`.
    """
    async with await Browser.launch(headless=True, stealth=True) as browser:
        tab = await browser.new_tab("about:blank")
        result = await tab.eval("chrome.runtime.sendMessage.toString()")
        assert result == "function sendMessage() { [native code] }"


@_skip_no_chrome
async def test_chrome_runtime_other_stubs_native_shape():
    """#11 — connect / addListener (nested) / postMessage (nested) all native shape."""
    async with await Browser.launch(headless=True, stealth=True) as browser:
        tab = await browser.new_tab("about:blank")
        result = await tab.eval("""
            (() => {
              const c = chrome.runtime.connect();
              return {
                connect: chrome.runtime.connect.toString(),
                addListener: c.onMessage.addListener.toString(),
                postMessage: c.postMessage.toString(),
              };
            })()
        """)
        assert result == {
            "connect": "function connect() { [native code] }",
            "addListener": "function addListener() { [native code] }",
            "postMessage": "function postMessage() { [native code] }",
        }


@_skip_no_chrome
async def test_chrome_runtime_toString_consistency_via_fpt():
    """#13 — Function.prototype.toString.call(stub) matches stub.toString()."""
    async with await Browser.launch(headless=True, stealth=True) as browser:
        tab = await browser.new_tab("about:blank")
        result = await tab.eval("""
            (() => {
              const fn = chrome.runtime.sendMessage;
              return {
                via_method: fn.toString(),
                via_fpt:    Function.prototype.toString.call(fn),
                equal:      fn.toString() === Function.prototype.toString.call(fn),
              };
            })()
        """)
        assert result["equal"] is True
        assert result["via_method"] == "function sendMessage() { [native code] }"


@_skip_no_chrome
async def test_oopif_chrome_runtime_native_shape():
    """#15 — chrome.runtime mask propagates into same-origin iframe.

    Uses a pre-existing iframe in initial HTML (same mechanism as test #14)
    because tellurium's CDP `addScriptToEvaluateOnNewDocument` propagates
    to iframes in the initial document load lifecycle but does NOT
    propagate to dynamically-appended iframes (documented as F7 gap).
    """
    async with await Browser.launch(headless=True, stealth=True) as browser:
        tab = await browser.new_tab(
            "data:text/html,<html><body><iframe id=t></iframe></body></html>"
        )
        # Small settle wait for the iframe realm initialization (matches #14).
        result = await tab.eval("""
            (async () => {
              await new Promise(r => setTimeout(r, 100));
              const w = document.getElementById('t').contentWindow;
              return w.chrome && w.chrome.runtime
                ? w.chrome.runtime.sendMessage.toString()
                : null;
            })()
        """)
        assert result == "function sendMessage() { [native code] }"
