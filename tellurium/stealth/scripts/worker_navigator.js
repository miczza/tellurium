(() => {
  // T7.7 P1.2 — worker-scope navigator parity.
  //
  // Empirically verified on Chrome 153 (stock, --remote-debugging-pipe):
  //   * `navigator.webdriver` does NOT exist in worker scope
  //     (`'webdriver' in self.navigator === false`, WorkerNavigator.prototype
  //     has no descriptor for it). Defining it here would CREATE a property
  //     that real Chrome does not have — a detection vector, not a fix.
  //     So this script deliberately does not touch `webdriver`.
  //   * `Emulation.setHardwareConcurrencyOverride` applied on the page
  //     session does NOT propagate to dedicated/shared/service workers:
  //     window reported 4 while the worker reported the real 22. That
  //     window/worker mismatch is the vector design doc 04 §P1.2 calls out
  //     ("il vero vettore e' il mismatch di proprieta' tra window e Worker").
  //
  // Injected via Runtime.evaluate into a worker target frozen by
  // Target.setAutoAttach(waitForDebuggerOnStart=true), i.e. before a single
  // line of the worker script has run.
  //
  // Follows the marker / toString-mask scheme of webdriver.js: an
  // object-literal accessor (name = 'get hardwareConcurrency', no
  // .prototype, non-constructable, throws TypeError on a foreign `this`)
  // plus a Function.prototype.toString mask that recognises the getter both
  // same-realm (identity) and cross-realm (marker comment in its source).
  const _WN_MARK = '__tellurium' + '_wnhc__';

  const _nav = navigator;

  const _hcHolder = {
    get hardwareConcurrency() {
      // __tellurium_wnhc__
      if (this !== _nav) throw new TypeError('Illegal invocation');
      return {{HARDWARE_CONCURRENCY}};
    },
  };
  const getHardwareConcurrency =
    Object.getOwnPropertyDescriptor(_hcHolder, 'hardwareConcurrency').get;

  Object.defineProperty(
    Object.getPrototypeOf(navigator), 'hardwareConcurrency', {
      get: getHardwareConcurrency,
      configurable: true,
      enumerable: true,
    });

  const originalToString = Function.prototype.toString;

  const _fakeToStringHolder = {
    toString() {
      // Same-realm fast paths.
      if (this === getHardwareConcurrency) {
        return 'function get hardwareConcurrency() { [native code] }';
      }
      if (this === fakeToString) {
        return 'function toString() { [native code] }';
      }

      const src = originalToString.call(this);
      if (typeof src !== 'string') return src;

      // Cross-realm peer fakeToString (nested workers): its source contains
      // the native-shape return literal verbatim.
      if (src.includes("'function get hardwareConcurrency() { [native code] }'")) {
        return 'function toString() { [native code] }';
      }

      // Cross-realm getter: identified by the marker comment in its body.
      // _WN_MARK is a split-string expression so this source does not
      // self-match the check above.
      if (src.includes(_WN_MARK)) {
        return 'function get hardwareConcurrency() { [native code] }';
      }

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
