(() => {
  const OrigRTC = window.RTCPeerConnection || window.webkitRTCPeerConnection;
  if (!OrigRTC) return;

  window.RTCPeerConnection = function(config, constraints) {
    if (config && config.iceServers) {
      config.iceServers = [];
    }
    const pc = new OrigRTC(config, constraints);

    const origSetLocal = pc.setLocalDescription.bind(pc);
    pc.setLocalDescription = function(desc) {
      if (desc && desc.sdp) {
        desc.sdp = desc.sdp.replace(/a=candidate:.*?\r\n/g, '');
      }
      return origSetLocal(desc);
    };
    return pc;
  };
  window.RTCPeerConnection.prototype = OrigRTC.prototype;
  window.webkitRTCPeerConnection = window.RTCPeerConnection;
})();
