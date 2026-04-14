(() => {
  const nativeToString = Function.prototype.toString;
  const overrides = new Map();

  const handler = {
    apply: function(target, thisArg, args) {
      if (overrides.has(thisArg)) {
        return overrides.get(thisArg);
      }
      return nativeToString.call(thisArg);
    }
  };

  Function.prototype.toString = new Proxy(nativeToString, handler);
  overrides.set(Function.prototype.toString, 'function toString() { [native code] }');

  // Helper to register masked functions
  window.__tellurium_mask = (fn, name) => {
    overrides.set(fn, `function ${name}() { [native code] }`);
  };
})();
