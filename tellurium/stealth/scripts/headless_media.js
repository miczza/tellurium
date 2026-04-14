(() => {
  if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
    const orig = navigator.mediaDevices.enumerateDevices;
    navigator.mediaDevices.enumerateDevices = async function() {
      const devices = await orig.call(this);
      if (devices.length === 0) {
        return [
          { deviceId: '', kind: 'audioinput', label: '', groupId: 'default' },
          { deviceId: '', kind: 'videoinput', label: '', groupId: 'default' },
          { deviceId: '', kind: 'audiooutput', label: '', groupId: 'default' },
        ];
      }
      return devices;
    };
  }
})();
