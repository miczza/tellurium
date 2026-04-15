(() => {
  const SPOOF_IP = "{{WEBRTC_PUBLIC_IP}}";
  const origRTCPC = window.RTCPeerConnection || window.webkitRTCPeerConnection;
  if (!origRTCPC) return;

  const wrapSetLocalDesc = (pc) => {
    const orig = pc.setLocalDescription.bind(pc);
    pc.setLocalDescription = (desc) => {
      if (desc && typeof desc.sdp === "string") {
        // When SPOOF_IP is unset, fall back to stripping all candidates — preserves
        // pre-review-2026-04-15 behavior for the has_proxy code path.
        if (!SPOOF_IP || SPOOF_IP === "null") {
          // No spoof IP: strip all host/srflx candidates to prevent leaking real IP
          desc = { type: desc.type, sdp: desc.sdp.replace(/a=candidate:.*?\r\n/g, '') };
        } else {
          // Replace real IPs in host/srflx ICE candidates with the spoofed IP.
          // Anchor to ^a=candidate: line starts (multiline) to avoid false-positive
          // rewrites on debug or extension SDP lines that happen to contain an IP.
          const newSdp = desc.sdp.replace(
            /^(a=candidate:\S+ \d+ \S+ \d+ )(\d+\.\d+\.\d+\.\d+)(\s+\d+\s+typ\s+(?:host|srflx))/gm,
            (_m, pre, _ip, post) => pre + SPOOF_IP + post
          );
          desc = { type: desc.type, sdp: newSdp };
        }
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
