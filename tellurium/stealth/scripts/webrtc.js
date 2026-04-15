(() => {
  const SPOOF_IP = "{{WEBRTC_PUBLIC_IP}}";
  const origRTCPC = window.RTCPeerConnection || window.webkitRTCPeerConnection;
  if (!origRTCPC) return;

  const wrapSetLocalDesc = (pc) => {
    const orig = pc.setLocalDescription.bind(pc);
    pc.setLocalDescription = (desc) => {
      if (desc && typeof desc.sdp === "string") {
        let sdp = desc.sdp;
        if (SPOOF_IP && SPOOF_IP !== "null") {
          // Replace real IPs in host/srflx ICE candidates with the spoofed IP
          sdp = sdp.replace(
            /(\d+\.\d+\.\d+\.\d+)(?=\s+\d+\s+typ\s+(?:host|srflx))/g,
            SPOOF_IP
          );
        } else {
          // No spoof IP: strip all host/srflx candidates to prevent leaking real IP
          sdp = sdp.replace(/a=candidate:.*?\r\n/g, '');
        }
        desc = new RTCSessionDescription({ type: desc.type, sdp: sdp });
      }
      return orig(desc);
    };
    return pc;
  };

  window.RTCPeerConnection = function(...args) {
    // Clear iceServers to prevent STUN/TURN lookups that could reveal the real IP
    if (args[0] && args[0].iceServers) {
      args[0] = Object.assign({}, args[0], { iceServers: [] });
    }
    const pc = new origRTCPC(...args);
    return wrapSetLocalDesc(pc);
  };
  window.RTCPeerConnection.prototype = origRTCPC.prototype;
  window.webkitRTCPeerConnection = window.RTCPeerConnection;
})();
