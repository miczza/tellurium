(() => {
  // T7.5: tellurium uses --remote-debugging-pipe transport which makes
  // navigator.webdriver natively true on controlled pages (unlike
  // --remote-debugging-port). JS override is required.
  //
  // CreepJS searchLies() flow for accessor properties:
  //   1. Tries proto[name] — must throw TypeError (like native getters do when
  //      called on a non-instance 'this'). If it returns a non-function value
  //      and is a lowercase property, CreepJS marks it as
  //      ['failed descriptor.value undefined'] regardless of queryLies.
  //   2. Falls into catch {} → reads the getter via getOwnPropertyDescriptor
  //   3. Passes apiFunction (the getter) to queryLies()
  //
  // Solution: use an object-literal `get webdriver()` accessor to get a function
  // that is non-constructable, has no .prototype, has name='get webdriver',
  // and throws TypeError when called with 'this' that is not the navigator
  // instance (i.e., when called as Navigator.prototype['webdriver']).
  //
  // Cross-realm masking: each realm's fakeToString identifies the webdriver
  // getter by a unique marker embedded in the getter's body comment.
  // The marker is split in fakeToString's source so it doesn't self-match.

  // Unique marker embedded in getter body (used for cross-realm identification).
  // Split across two strings so fakeToString's own source doesn't match itself.
  const _WD_MARK = '__tellurium' + '_wd__';

  // T7.6 F1: chrome.runtime stub markers. Joined at runtime; the joined
  // literal does NOT appear in fakeToString's source, only the split-string
  // expression does. The actual stubs in chrome_runtime.js DO contain the
  // joined literal as a body comment, so src.includes() matches them.
  const _CR_PREFIX = '__tellurium' + '_chrome_';
  const _CR_CONNECT = _CR_PREFIX + 'connect__';
  const _CR_SEND    = _CR_PREFIX + 'sendMessage__';
  const _CR_ADD_LISTENER = _CR_PREFIX + 'addListener__';
  const _CR_POST    = _CR_PREFIX + 'postMessage__';

  // Capture reference to the realm's navigator for the Illegal-invocation check.
  // T7.6 F5: we use strict-equal (`this !== _nav`) instead of
  // `instanceof Navigator` because `Navigator` is a global lookup that an
  // attacker can shadow, while `_nav` is a closure binding unreachable from
  // outside this IIFE. Strict-equal on a closure-captured reference is more
  // defensible than `instanceof` against an active threat model.
  // See tests/stealth/test_webdriver_robustness.py::test_webdriver_getter_wrong_this_throws
  // for the wrong-this TypeError invariant that holds regardless of choice.
  const _nav = navigator;

  // Create getter via object-literal accessor — results in a function with:
  //   name = 'get webdriver', no .prototype, non-constructable.
  // The comment inside the body contains the marker text verbatim so
  // originalToString on this function returns a source that includes _WD_MARK.
  const _wdHolder = {
    get webdriver() {
      // __tellurium_wd__
      if (this !== _nav) throw new TypeError('Illegal invocation');
      return false;
    },
  };
  const getWebDriver = Object.getOwnPropertyDescriptor(_wdHolder, 'webdriver').get;

  Object.defineProperty(Object.getPrototypeOf(navigator), 'webdriver', {
    get: getWebDriver,
    configurable: true,
    enumerable: true,
  });

  const originalToString = Function.prototype.toString;

  // Use method shorthand so:
  //   'prototype' in fakeToString === false  (native FPT has no .prototype)
  //   new fakeToString()                     throws TypeError (non-constructable)
  //   Object.getOwnPropertyNames(fakeToString) === ['length','name']
  const _fakeToStringHolder = {
    toString() {
      // Same-realm fast paths
      if (this === getWebDriver) {
        return 'function get webdriver() { [native code] }';
      }
      if (this === fakeToString) {
        return 'function toString() { [native code] }';
      }

      const src = originalToString.call(this);
      if (typeof src !== 'string') return src;

      // Cross-realm fakeToString self-match. Each realm's fakeToString source
      // contains every native-shape return-value literal as part of its return
      // statements; matching any of them identifies a peer fakeToString from
      // another realm. The marker checks below correctly miss on a peer
      // fakeToString today (the joined marker text never appears in
      // fakeToString source — only the split-string expressions and variable
      // references do), so the order here is defensive rather than strictly
      // required. Keeping self-match first short-circuits any future case
      // where a peer's source happens to contain marker text.
      if (src.includes("'function get webdriver() { [native code] }'") ||
          src.includes("'function connect() { [native code] }'") ||
          src.includes("'function sendMessage() { [native code] }'") ||
          src.includes("'function addListener() { [native code] }'") ||
          src.includes("'function postMessage() { [native code] }'")) {
        return 'function toString() { [native code] }';
      }

      // Cross-realm webdriver getter: each realm's getWebDriver contains the
      // marker comment in its body. _WD_MARK is split-string so fakeToString's
      // own source does not match this check.
      if (src.includes(_WD_MARK)) {
        return 'function get webdriver() { [native code] }';
      }

      // T7.6 F1: cross-realm chrome.runtime stub identification.
      // Each marker is a runtime-joined string (split-string in fakeToString
      // source) so fakeToString itself doesn't false-match.
      if (src.includes(_CR_CONNECT)) return 'function connect() { [native code] }';
      if (src.includes(_CR_SEND))    return 'function sendMessage() { [native code] }';
      if (src.includes(_CR_ADD_LISTENER)) return 'function addListener() { [native code] }';
      if (src.includes(_CR_POST))    return 'function postMessage() { [native code] }';

      return src;
    },
  };
  const fakeToString = _fakeToStringHolder.toString;

  Object.defineProperty(Function.prototype, 'toString', {
    value: fakeToString,
    configurable: true,
    writable: true,
  });
})();
