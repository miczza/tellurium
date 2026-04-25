(() => {
  if (!window.chrome) {
    window.chrome = {};
  }
  if (!window.chrome.runtime) {
    window.chrome.runtime = {
      // T7.5: arrow functions don't have .prototype, matching native bindings.
      // CreepJS check: `'prototype' in chrome.runtime.sendMessage` => false.
      connect: () => ({
        onMessage: { addListener: () => {} },
        postMessage: () => {},
      }),
      sendMessage: () => {},
      id: undefined,
    };
  }
})();
