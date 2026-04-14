(() => {
  const LOCALE = '{{LOCALE}}';
  const LAYOUTS = {
    'en-US': { KeyA: 'a', KeyB: 'b', KeyC: 'c', KeyD: 'd', KeyE: 'e', KeyF: 'f', KeyG: 'g', KeyH: 'h', KeyI: 'i', KeyJ: 'j', KeyK: 'k', KeyL: 'l', KeyM: 'm', KeyN: 'n', KeyO: 'o', KeyP: 'p', KeyQ: 'q', KeyR: 'r', KeyS: 's', KeyT: 't', KeyU: 'u', KeyV: 'v', KeyW: 'w', KeyX: 'x', KeyY: 'y', KeyZ: 'z' },
    'de-DE': { KeyA: 'a', KeyB: 'b', KeyC: 'c', KeyD: 'd', KeyE: 'e', KeyF: 'f', KeyG: 'g', KeyH: 'h', KeyI: 'i', KeyJ: 'j', KeyK: 'k', KeyL: 'l', KeyM: 'm', KeyN: 'n', KeyO: 'o', KeyP: 'p', KeyQ: 'q', KeyR: 'r', KeyS: 's', KeyT: 't', KeyU: 'u', KeyV: 'v', KeyW: 'w', KeyX: 'x', KeyY: 'z', KeyZ: 'y' },
  };
  const layout = LAYOUTS[LOCALE] || LAYOUTS['en-US'];
  if (navigator.keyboard && navigator.keyboard.getLayoutMap) {
    const orig = navigator.keyboard.getLayoutMap;
    navigator.keyboard.getLayoutMap = async function() {
      return new Map(Object.entries(layout));
    };
  }
})();
