(() => {
  const HC = {{HARDWARE_CONCURRENCY}};
  const DM = {{DEVICE_MEMORY}};
  const PLAT = '{{PLATFORM}}';
  const proto = Object.getPrototypeOf(navigator);
  Object.defineProperty(proto, 'hardwareConcurrency', {
    get: () => HC, configurable: true,
  });
  Object.defineProperty(proto, 'deviceMemory', {
    get: () => DM, configurable: true,
  });
  Object.defineProperty(proto, 'platform', {
    get: () => PLAT, configurable: true,
  });
})();
