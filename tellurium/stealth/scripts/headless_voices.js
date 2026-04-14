(() => {
  const OS = '{{OS}}';
  const voiceData = {
    windows: [
      { name: 'Microsoft David', lang: 'en-US', default: true },
      { name: 'Microsoft Zira', lang: 'en-US', default: false },
    ],
    macos: [
      { name: 'Alex', lang: 'en-US', default: true },
      { name: 'Samantha', lang: 'en-US', default: false },
    ],
    linux: [
      { name: 'English (America)', lang: 'en-US', default: true },
    ],
  };
  const voices = (voiceData[OS] || voiceData['linux']).map(v => {
    const voice = Object.create(SpeechSynthesisVoice.prototype);
    Object.defineProperties(voice, {
      name: { value: v.name, enumerable: true },
      lang: { value: v.lang, enumerable: true },
      default: { value: v.default, enumerable: true },
      localService: { value: true, enumerable: true },
      voiceURI: { value: v.name, enumerable: true },
    });
    return voice;
  });
  if (window.speechSynthesis) {
    const orig = speechSynthesis.getVoices;
    speechSynthesis.getVoices = function() {
      const real = orig.call(this);
      return real.length > 0 ? real : voices;
    };
  }
})();
