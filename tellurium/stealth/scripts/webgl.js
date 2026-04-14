(() => {
  const VENDOR = '{{VENDOR}}';
  const RENDERER = '{{RENDERER}}';
  const getParameter = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = function(param) {
    if (param === 37445) return VENDOR;   // UNMASKED_VENDOR_WEBGL
    if (param === 37446) return RENDERER; // UNMASKED_RENDERER_WEBGL
    return getParameter.call(this, param);
  };
  if (typeof WebGL2RenderingContext !== 'undefined') {
    const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
    WebGL2RenderingContext.prototype.getParameter = function(param) {
      if (param === 37445) return VENDOR;
      if (param === 37446) return RENDERER;
      return getParameter2.call(this, param);
    };
  }
})();
