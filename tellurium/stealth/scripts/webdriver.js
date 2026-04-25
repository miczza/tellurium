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

  // Capture reference to the realm's navigator for the Illegal invocation check
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

      // Cross-realm webdriver getter: each realm's getWebDriver contains the
      // marker comment in its body. _WD_MARK is split so fakeToString's own
      // source does not match this check.
      if (typeof src === 'string' && src.includes(_WD_MARK)) {
        return 'function get webdriver() { [native code] }';
      }

      // Cross-realm fakeToString: when CreepJS calls scope_FPT on the
      // main window's fakeToString, the source will contain our unique
      // literal. Return the native-shape string for it.
      if (typeof src === 'string' &&
          src.includes("'function get webdriver() { [native code] }'")) {
        return 'function toString() { [native code] }';
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
