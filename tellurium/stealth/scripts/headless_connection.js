(() => {
  if (!navigator.connection) {
    Object.defineProperty(navigator, 'connection', {
      get: () => ({
        effectiveType: '4g', rtt: 50, downlink: 10,
        saveData: false, onchange: null,
      }),
      configurable: true,
    });
  }
})();
