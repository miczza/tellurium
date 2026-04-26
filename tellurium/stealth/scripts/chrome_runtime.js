(() => {
  if (!window.chrome) {
    window.chrome = {};
  }
  if (!window.chrome.runtime) {
    // T7.5: arrow functions don't have .prototype, matching native bindings.
    // CreepJS check: `'prototype' in chrome.runtime.sendMessage` => false.
    //
    // T7.6 F1: each stub embeds a unique body-comment marker so webdriver.js's
    // fakeToString recognises it cross-realm and returns the native-shape
    // string instead of "() => { /* ... */ }". Markers use the same shape
    // as webdriver.js's _WD_MARK so that the two scripts stay in sync.
    window.chrome.runtime = {
      connect: () => { /* __tellurium_chrome_connect__ */
        return {
          onMessage: { addListener: () => { /* __tellurium_chrome_addListener__ */ } },
          postMessage: () => { /* __tellurium_chrome_postMessage__ */ },
        };
      },
      sendMessage: () => { /* __tellurium_chrome_sendMessage__ */ },
      id: undefined,
    };
  }
})();
