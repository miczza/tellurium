"""Auto-generated CDP bindings for the Browser domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from tellurium.cdp.types import T_JSON_DICT


class BrowserContextID(str):
    """CDP string type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> BrowserContextID:
        return cls(val)


class WindowID(int):
    """CDP type alias."""

    def to_json(self) -> int:
        return int(self)

    @classmethod
    def from_json(cls, val: int) -> WindowID:
        return cls(val)


class WindowState(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> WindowState:
        return cls(val)


@dataclass
class Bounds:
    left: Optional[int] = None
    top: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    window_state: Optional[WindowState] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        if self.left is not None:
            d['left'] = self.left
        if self.top is not None:
            d['top'] = self.top
        if self.width is not None:
            d['width'] = self.width
        if self.height is not None:
            d['height'] = self.height
        if self.window_state is not None:
            d['windowState'] = self.window_state.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> Bounds:
        return cls(
            left=int(data['left']) if 'left' in data else None,
            top=int(data['top']) if 'top' in data else None,
            width=int(data['width']) if 'width' in data else None,
            height=int(data['height']) if 'height' in data else None,
            window_state=WindowState.from_json(data['windowState']) if 'windowState' in data else None,
        )


class PermissionType(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> PermissionType:
        return cls(val)


class PermissionSetting(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> PermissionSetting:
        return cls(val)


@dataclass
class PermissionDescriptor:
    name: str
    sysex: Optional[bool] = None
    user_visible_only: Optional[bool] = None
    allow_without_sanitization: Optional[bool] = None
    allow_without_gesture: Optional[bool] = None
    pan_tilt_zoom: Optional[bool] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['name'] = name
        if self.sysex is not None:
            d['sysex'] = self.sysex
        if self.user_visible_only is not None:
            d['userVisibleOnly'] = self.user_visible_only
        if self.allow_without_sanitization is not None:
            d['allowWithoutSanitization'] = self.allow_without_sanitization
        if self.allow_without_gesture is not None:
            d['allowWithoutGesture'] = self.allow_without_gesture
        if self.pan_tilt_zoom is not None:
            d['panTiltZoom'] = self.pan_tilt_zoom
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> PermissionDescriptor:
        return cls(
            name=str(data['name']),
            sysex=bool(data['sysex']) if 'sysex' in data else None,
            user_visible_only=bool(data['userVisibleOnly']) if 'userVisibleOnly' in data else None,
            allow_without_sanitization=bool(data['allowWithoutSanitization']) if 'allowWithoutSanitization' in data else None,
            allow_without_gesture=bool(data['allowWithoutGesture']) if 'allowWithoutGesture' in data else None,
            pan_tilt_zoom=bool(data['panTiltZoom']) if 'panTiltZoom' in data else None,
        )


class BrowserCommandId(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> BrowserCommandId:
        return cls(val)


@dataclass
class Bucket:
    low: int
    high: int
    count: int

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['low'] = low
        d['high'] = high
        d['count'] = count
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> Bucket:
        return cls(
            low=int(data['low']),
            high=int(data['high']),
            count=int(data['count']),
        )


@dataclass
class Histogram:
    name: str
    sum: int
    count: int
    buckets: list[Bucket]

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['name'] = name
        d['sum'] = sum
        d['count'] = count
        d['buckets'] = [i.to_json() for i in buckets]
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> Histogram:
        return cls(
            name=str(data['name']),
            sum=int(data['sum']),
            count=int(data['count']),
            buckets=[Bucket.from_json(i) for i in data['buckets']],
        )


class PrivacySandboxAPI(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> PrivacySandboxAPI:
        return cls(val)


def set_permission(permission: PermissionDescriptor, setting: PermissionSetting, origin: Optional[str] = None, embedded_origin: Optional[str] = None, browser_context_id: Optional[BrowserContextID] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['permission'] = permission.to_json()
    params['setting'] = setting.to_json()
    if origin is not None:
        params['origin'] = origin
    if embedded_origin is not None:
        params['embeddedOrigin'] = embedded_origin
    if browser_context_id is not None:
        params['browserContextId'] = browser_context_id.to_json()
    cmd: T_JSON_DICT = {"method": "Browser.setPermission", "params": params}
    return cmd, None


def grant_permissions(permissions: list[PermissionType], origin: Optional[str] = None, browser_context_id: Optional[BrowserContextID] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['permissions'] = [i.to_json() for i in permissions]
    if origin is not None:
        params['origin'] = origin
    if browser_context_id is not None:
        params['browserContextId'] = browser_context_id.to_json()
    cmd: T_JSON_DICT = {"method": "Browser.grantPermissions", "params": params}
    return cmd, None


def reset_permissions(browser_context_id: Optional[BrowserContextID] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    if browser_context_id is not None:
        params['browserContextId'] = browser_context_id.to_json()
    cmd: T_JSON_DICT = {"method": "Browser.resetPermissions", "params": params}
    return cmd, None


def set_download_behavior(behavior: str, browser_context_id: Optional[BrowserContextID] = None, download_path: Optional[str] = None, events_enabled: Optional[bool] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['behavior'] = behavior
    if browser_context_id is not None:
        params['browserContextId'] = browser_context_id.to_json()
    if download_path is not None:
        params['downloadPath'] = download_path
    if events_enabled is not None:
        params['eventsEnabled'] = events_enabled
    cmd: T_JSON_DICT = {"method": "Browser.setDownloadBehavior", "params": params}
    return cmd, None


def cancel_download(guid: str, browser_context_id: Optional[BrowserContextID] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['guid'] = guid
    if browser_context_id is not None:
        params['browserContextId'] = browser_context_id.to_json()
    cmd: T_JSON_DICT = {"method": "Browser.cancelDownload", "params": params}
    return cmd, None


def close() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Browser.close", "params": params}
    return cmd, None


def crash() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Browser.crash", "params": params}
    return cmd, None


def crash_gpu_process() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Browser.crashGpuProcess", "params": params}
    return cmd, None


@dataclass
class GetVersionResult:
    protocol_version: str
    product: str
    revision: str
    user_agent: str
    js_version: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetVersionResult:
        return cls(
            protocol_version=str(data['protocolVersion']),
            product=str(data['product']),
            revision=str(data['revision']),
            user_agent=str(data['userAgent']),
            js_version=str(data['jsVersion']),
        )


def get_version() -> tuple[T_JSON_DICT, type[GetVersionResult]]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Browser.getVersion", "params": params}
    return cmd, GetVersionResult


@dataclass
class GetBrowserCommandLineResult:
    arguments: list[str]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetBrowserCommandLineResult:
        return cls(
            arguments=[str(i) for i in data['arguments']],
        )


def get_browser_command_line() -> tuple[T_JSON_DICT, type[GetBrowserCommandLineResult]]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Browser.getBrowserCommandLine", "params": params}
    return cmd, GetBrowserCommandLineResult


@dataclass
class GetHistogramsResult:
    histograms: list[Histogram]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetHistogramsResult:
        return cls(
            histograms=[Histogram.from_json(i) for i in data['histograms']],
        )


def get_histograms(query: Optional[str] = None, delta: Optional[bool] = None) -> tuple[T_JSON_DICT, type[GetHistogramsResult]]:
    params: T_JSON_DICT = {}
    if query is not None:
        params['query'] = query
    if delta is not None:
        params['delta'] = delta
    cmd: T_JSON_DICT = {"method": "Browser.getHistograms", "params": params}
    return cmd, GetHistogramsResult


@dataclass
class GetHistogramResult:
    histogram: Histogram

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetHistogramResult:
        return cls(
            histogram=Histogram.from_json(data['histogram']),
        )


def get_histogram(name: str, delta: Optional[bool] = None) -> tuple[T_JSON_DICT, type[GetHistogramResult]]:
    params: T_JSON_DICT = {}
    params['name'] = name
    if delta is not None:
        params['delta'] = delta
    cmd: T_JSON_DICT = {"method": "Browser.getHistogram", "params": params}
    return cmd, GetHistogramResult


@dataclass
class GetWindowBoundsResult:
    bounds: Bounds

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetWindowBoundsResult:
        return cls(
            bounds=Bounds.from_json(data['bounds']),
        )


def get_window_bounds(window_id: WindowID) -> tuple[T_JSON_DICT, type[GetWindowBoundsResult]]:
    params: T_JSON_DICT = {}
    params['windowId'] = window_id.to_json()
    cmd: T_JSON_DICT = {"method": "Browser.getWindowBounds", "params": params}
    return cmd, GetWindowBoundsResult


@dataclass
class GetWindowForTargetResult:
    window_id: WindowID
    bounds: Bounds

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetWindowForTargetResult:
        return cls(
            window_id=WindowID.from_json(data['windowId']),
            bounds=Bounds.from_json(data['bounds']),
        )


def get_window_for_target(target_id: Optional[TargetID] = None) -> tuple[T_JSON_DICT, type[GetWindowForTargetResult]]:
    params: T_JSON_DICT = {}
    if target_id is not None:
        params['targetId'] = target_id.to_json()
    cmd: T_JSON_DICT = {"method": "Browser.getWindowForTarget", "params": params}
    return cmd, GetWindowForTargetResult


def set_window_bounds(window_id: WindowID, bounds: Bounds) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['windowId'] = window_id.to_json()
    params['bounds'] = bounds.to_json()
    cmd: T_JSON_DICT = {"method": "Browser.setWindowBounds", "params": params}
    return cmd, None


def set_contents_size(window_id: WindowID, width: Optional[int] = None, height: Optional[int] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['windowId'] = window_id.to_json()
    if width is not None:
        params['width'] = width
    if height is not None:
        params['height'] = height
    cmd: T_JSON_DICT = {"method": "Browser.setContentsSize", "params": params}
    return cmd, None


def set_dock_tile(badge_label: Optional[str] = None, image: Optional[str] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    if badge_label is not None:
        params['badgeLabel'] = badge_label
    if image is not None:
        params['image'] = image
    cmd: T_JSON_DICT = {"method": "Browser.setDockTile", "params": params}
    return cmd, None


def execute_browser_command(command_id: BrowserCommandId) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['commandId'] = command_id.to_json()
    cmd: T_JSON_DICT = {"method": "Browser.executeBrowserCommand", "params": params}
    return cmd, None


def add_privacy_sandbox_enrollment_override(url: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['url'] = url
    cmd: T_JSON_DICT = {"method": "Browser.addPrivacySandboxEnrollmentOverride", "params": params}
    return cmd, None


def add_privacy_sandbox_coordinator_key_config(api: PrivacySandboxAPI, coordinator_origin: str, key_config: str, browser_context_id: Optional[BrowserContextID] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['api'] = api.to_json()
    params['coordinatorOrigin'] = coordinator_origin
    params['keyConfig'] = key_config
    if browser_context_id is not None:
        params['browserContextId'] = browser_context_id.to_json()
    cmd: T_JSON_DICT = {"method": "Browser.addPrivacySandboxCoordinatorKeyConfig", "params": params}
    return cmd, None


@dataclass
class DownloadWillBegin:
    EVENT_NAME: str = field(init=False, repr=False, default="Browser.downloadWillBegin")
    frame_id: FrameId
    guid: str
    url: str
    suggested_filename: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DownloadWillBegin:
        return cls(
            frame_id=FrameId.from_json(data['frameId']),
            guid=str(data['guid']),
            url=str(data['url']),
            suggested_filename=str(data['suggestedFilename']),
        )


@dataclass
class DownloadProgress:
    EVENT_NAME: str = field(init=False, repr=False, default="Browser.downloadProgress")
    guid: str
    total_bytes: float
    received_bytes: float
    state: str
    file_path: Optional[str] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DownloadProgress:
        return cls(
            guid=str(data['guid']),
            total_bytes=float(data['totalBytes']),
            received_bytes=float(data['receivedBytes']),
            state=str(data['state']),
            file_path=str(data['filePath']) if 'filePath' in data else None,
        )

