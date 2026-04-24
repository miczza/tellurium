(() => {
  // Match nodriver: return false (spec-compliant) rather than undefined.
  // Attempting to delete first handles the case where the prototype getter
  // is configurable (Chrome typically is), collapsing to the spec default.
  // Fallback override on the prototype ensures the value is visible as false
  // across all frames that inherit Navigator.prototype.
  try {
    delete Object.getPrototypeOf(navigator).webdriver;
  } catch (e) { /* swallow; fallback below handles it */ }
  if (navigator.webdriver !== false) {
    Object.defineProperty(Object.getPrototypeOf(navigator), 'webdriver', {
      get: () => false,
      configurable: true,
      enumerable: true,
    });
  }
})();
