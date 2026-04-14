(() => {
  const W = {{OUTER_WIDTH}};
  const H = {{OUTER_HEIGHT}};
  Object.defineProperty(window, 'outerWidth', { get: () => W });
  Object.defineProperty(window, 'outerHeight', { get: () => H });
})();
