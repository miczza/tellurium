(() => {
  if (typeof Notification !== 'undefined') {
    Object.defineProperty(Notification, 'permission', {
      get: () => 'default', configurable: true,
    });
  }
})();
