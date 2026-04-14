"""Real GPU profiles per OS for WebGL spoofing."""

GPU_PROFILES = {
    "windows": [
        {"weight": 0.15, "vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
        {"weight": 0.12, "vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
        {"weight": 0.10, "vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
        {"weight": 0.10, "vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4060 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
        {"weight": 0.08, "vendor": "Google Inc. (AMD)", "renderer": "ANGLE (AMD, AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
        {"weight": 0.08, "vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel, Intel(R) UHD Graphics 770 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
        {"weight": 0.07, "vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
        {"weight": 0.06, "vendor": "Google Inc. (AMD)", "renderer": "ANGLE (AMD, AMD Radeon RX 6600 XT Direct3D11 vs_5_0 ps_5_0, D3D11)"},
        {"weight": 0.05, "vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel, Intel(R) Iris Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    ],
    "macos": [
        {"weight": 0.40, "vendor": "Google Inc. (Apple)", "renderer": "ANGLE (Apple, ANGLE Metal Renderer: Apple M1, Unspecified Version)"},
        {"weight": 0.25, "vendor": "Google Inc. (Apple)", "renderer": "ANGLE (Apple, ANGLE Metal Renderer: Apple M2, Unspecified Version)"},
        {"weight": 0.15, "vendor": "Google Inc. (Apple)", "renderer": "ANGLE (Apple, ANGLE Metal Renderer: Apple M3, Unspecified Version)"},
        {"weight": 0.10, "vendor": "Google Inc. (Apple)", "renderer": "ANGLE (Apple, ANGLE Metal Renderer: Apple M1 Pro, Unspecified Version)"},
        {"weight": 0.10, "vendor": "Google Inc. (Apple)", "renderer": "ANGLE (Apple, ANGLE Metal Renderer: Apple M2 Pro, Unspecified Version)"},
    ],
    "linux": [
        {"weight": 0.30, "vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel, Mesa Intel(R) UHD Graphics 630 (CFL GT2), OpenGL 4.6)"},
        {"weight": 0.25, "vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060/PCIe/SSE2, OpenGL 4.6.0)"},
        {"weight": 0.15, "vendor": "Google Inc. (AMD)", "renderer": "ANGLE (AMD, AMD Radeon RX 580, OpenGL 4.6)"},
        {"weight": 0.15, "vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel, Mesa Intel(R) UHD Graphics 770 (ADL-S GT1), OpenGL 4.6)"},
        {"weight": 0.15, "vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER/PCIe/SSE2, OpenGL 4.6.0)"},
    ],
}
