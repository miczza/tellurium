(() => {
  const pluginData = [
    { name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
    { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', description: '' },
    { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: '' },
    { name: 'Microsoft Edge PDF Viewer', filename: 'internal-pdf-viewer', description: '' },
    { name: 'WebKit built-in PDF', filename: 'internal-pdf-viewer', description: '' },
  ];
  const mimeType = { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format' };

  if (navigator.plugins.length === 0) {
    const fakePlugins = pluginData.map(p => {
      const plugin = Object.create(Plugin.prototype);
      Object.defineProperties(plugin, {
        name: { value: p.name, enumerable: true },
        filename: { value: p.filename, enumerable: true },
        description: { value: p.description, enumerable: true },
        length: { value: 1, enumerable: true },
        0: { value: mimeType },
      });
      return plugin;
    });
    Object.defineProperty(navigator, 'plugins', {
      get: () => fakePlugins,
      configurable: true,
    });
  }
})();
