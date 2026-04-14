"""Auto-generated CDP bindings for the Target domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from tellurium.cdp.types import T_JSON_DICT


class TargetID(str):
    """CDP string type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> TargetID:
        return cls(val)


class SessionID(str):
    """CDP string type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> SessionID:
        return cls(val)


@dataclass
class TargetInfo:
    target_id: TargetID
    type: str
    title: str
    url: str
    attached: bool
    can_access_opener: bool
    opener_id: Optional[TargetID] = None
    opener_frame_id: Optional[FrameId] = None
    parent_frame_id: Optional[FrameId] = None
    browser_context_id: Optional[BrowserContextID] = None
    subtype: Optional[str] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['targetId'] = target_id.to_json()
        d['type'] = type
        d['title'] = title
        d['url'] = url
        d['attached'] = attached
        d['canAccessOpener'] = can_access_opener
        if self.opener_id is not None:
            d['openerId'] = self.opener_id.to_json()
        if self.opener_frame_id is not None:
            d['openerFrameId'] = self.opener_frame_id.to_json()
        if self.parent_frame_id is not None:
            d['parentFrameId'] = self.parent_frame_id.to_json()
        if self.browser_context_id is not None:
            d['browserContextId'] = self.browser_context_id.to_json()
        if self.subtype is not None:
            d['subtype'] = self.subtype
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> TargetInfo:
        return cls(
            target_id=TargetID.from_json(data['targetId']),
            type=str(data['type']),
            title=str(data['title']),
            url=str(data['url']),
            attached=bool(data['attached']),
            can_access_opener=bool(data['canAccessOpener']),
            opener_id=TargetID.from_json(data['openerId']) if 'openerId' in data else None,
            opener_frame_id=FrameId.from_json(data['openerFrameId']) if 'openerFrameId' in data else None,
            parent_frame_id=FrameId.from_json(data['parentFrameId']) if 'parentFrameId' in data else None,
            browser_context_id=BrowserContextID.from_json(data['browserContextId']) if 'browserContextId' in data else None,
            subtype=str(data['subtype']) if 'subtype' in data else None,
        )


@dataclass
class FilterEntry:
    exclude: Optional[bool] = None
    type: Optional[str] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        if self.exclude is not None:
            d['exclude'] = self.exclude
        if self.type is not None:
            d['type'] = self.type
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> FilterEntry:
        return cls(
            exclude=bool(data['exclude']) if 'exclude' in data else None,
            type=str(data['type']) if 'type' in data else None,
        )


class TargetFilter(Any):
    """CDP type alias."""

    def to_json(self) -> Any:
        return Any(self)

    @classmethod
    def from_json(cls, val: Any) -> TargetFilter:
        return cls(val)


@dataclass
class RemoteLocation:
    host: str
    port: int

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['host'] = host
        d['port'] = port
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> RemoteLocation:
        return cls(
            host=str(data['host']),
            port=int(data['port']),
        )


class WindowState(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> WindowState:
        return cls(val)


def activate_target(target_id: TargetID) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['targetId'] = target_id.to_json()
    cmd: T_JSON_DICT = {"method": "Target.activateTarget", "params": params}
    return cmd, None


@dataclass
class AttachToTargetResult:
    session_id: SessionID

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> AttachToTargetResult:
        return cls(
            session_id=SessionID.from_json(data['sessionId']),
        )


def attach_to_target(target_id: TargetID, flatten: Optional[bool] = None) -> tuple[T_JSON_DICT, type[AttachToTargetResult]]:
    params: T_JSON_DICT = {}
    params['targetId'] = target_id.to_json()
    if flatten is not None:
        params['flatten'] = flatten
    cmd: T_JSON_DICT = {"method": "Target.attachToTarget", "params": params}
    return cmd, AttachToTargetResult


@dataclass
class AttachToBrowserTargetResult:
    session_id: SessionID

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> AttachToBrowserTargetResult:
        return cls(
            session_id=SessionID.from_json(data['sessionId']),
        )


def attach_to_browser_target() -> tuple[T_JSON_DICT, type[AttachToBrowserTargetResult]]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Target.attachToBrowserTarget", "params": params}
    return cmd, AttachToBrowserTargetResult


@dataclass
class CloseTargetResult:
    success: bool

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CloseTargetResult:
        return cls(
            success=bool(data['success']),
        )


def close_target(target_id: TargetID) -> tuple[T_JSON_DICT, type[CloseTargetResult]]:
    params: T_JSON_DICT = {}
    params['targetId'] = target_id.to_json()
    cmd: T_JSON_DICT = {"method": "Target.closeTarget", "params": params}
    return cmd, CloseTargetResult


def expose_dev_tools_protocol(target_id: TargetID, binding_name: Optional[str] = None, inherit_permissions: Optional[bool] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['targetId'] = target_id.to_json()
    if binding_name is not None:
        params['bindingName'] = binding_name
    if inherit_permissions is not None:
        params['inheritPermissions'] = inherit_permissions
    cmd: T_JSON_DICT = {"method": "Target.exposeDevToolsProtocol", "params": params}
    return cmd, None


@dataclass
class CreateBrowserContextResult:
    browser_context_id: BrowserContextID

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CreateBrowserContextResult:
        return cls(
            browser_context_id=BrowserContextID.from_json(data['browserContextId']),
        )


def create_browser_context(dispose_on_detach: Optional[bool] = None, proxy_server: Optional[str] = None, proxy_bypass_list: Optional[str] = None, origins_with_universal_network_access: Optional[list[str]] = None) -> tuple[T_JSON_DICT, type[CreateBrowserContextResult]]:
    params: T_JSON_DICT = {}
    if dispose_on_detach is not None:
        params['disposeOnDetach'] = dispose_on_detach
    if proxy_server is not None:
        params['proxyServer'] = proxy_server
    if proxy_bypass_list is not None:
        params['proxyBypassList'] = proxy_bypass_list
    if origins_with_universal_network_access is not None:
        params['originsWithUniversalNetworkAccess'] = list(origins_with_universal_network_access)
    cmd: T_JSON_DICT = {"method": "Target.createBrowserContext", "params": params}
    return cmd, CreateBrowserContextResult


@dataclass
class GetBrowserContextsResult:
    browser_context_ids: list[BrowserContextID]
    default_browser_context_id: Optional[BrowserContextID] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetBrowserContextsResult:
        return cls(
            browser_context_ids=[BrowserContextID.from_json(i) for i in data['browserContextIds']],
            default_browser_context_id=BrowserContextID.from_json(data['defaultBrowserContextId']) if 'defaultBrowserContextId' in data else None,
        )


def get_browser_contexts() -> tuple[T_JSON_DICT, type[GetBrowserContextsResult]]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Target.getBrowserContexts", "params": params}
    return cmd, GetBrowserContextsResult


@dataclass
class CreateTargetResult:
    target_id: TargetID

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CreateTargetResult:
        return cls(
            target_id=TargetID.from_json(data['targetId']),
        )


def create_target(url: str, left: Optional[int] = None, top: Optional[int] = None, width: Optional[int] = None, height: Optional[int] = None, window_state: Optional[WindowState] = None, browser_context_id: Optional[BrowserContextID] = None, enable_begin_frame_control: Optional[bool] = None, new_window: Optional[bool] = None, background: Optional[bool] = None, for_tab: Optional[bool] = None, hidden: Optional[bool] = None, focus: Optional[bool] = None) -> tuple[T_JSON_DICT, type[CreateTargetResult]]:
    params: T_JSON_DICT = {}
    params['url'] = url
    if left is not None:
        params['left'] = left
    if top is not None:
        params['top'] = top
    if width is not None:
        params['width'] = width
    if height is not None:
        params['height'] = height
    if window_state is not None:
        params['windowState'] = window_state.to_json()
    if browser_context_id is not None:
        params['browserContextId'] = browser_context_id.to_json()
    if enable_begin_frame_control is not None:
        params['enableBeginFrameControl'] = enable_begin_frame_control
    if new_window is not None:
        params['newWindow'] = new_window
    if background is not None:
        params['background'] = background
    if for_tab is not None:
        params['forTab'] = for_tab
    if hidden is not None:
        params['hidden'] = hidden
    if focus is not None:
        params['focus'] = focus
    cmd: T_JSON_DICT = {"method": "Target.createTarget", "params": params}
    return cmd, CreateTargetResult


def detach_from_target(session_id: Optional[SessionID] = None, target_id: Optional[TargetID] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    if session_id is not None:
        params['sessionId'] = session_id.to_json()
    if target_id is not None:
        params['targetId'] = target_id.to_json()
    cmd: T_JSON_DICT = {"method": "Target.detachFromTarget", "params": params}
    return cmd, None


def dispose_browser_context(browser_context_id: BrowserContextID) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['browserContextId'] = browser_context_id.to_json()
    cmd: T_JSON_DICT = {"method": "Target.disposeBrowserContext", "params": params}
    return cmd, None


@dataclass
class GetTargetInfoResult:
    target_info: TargetInfo

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetTargetInfoResult:
        return cls(
            target_info=TargetInfo.from_json(data['targetInfo']),
        )


def get_target_info(target_id: Optional[TargetID] = None) -> tuple[T_JSON_DICT, type[GetTargetInfoResult]]:
    params: T_JSON_DICT = {}
    if target_id is not None:
        params['targetId'] = target_id.to_json()
    cmd: T_JSON_DICT = {"method": "Target.getTargetInfo", "params": params}
    return cmd, GetTargetInfoResult


@dataclass
class GetTargetsResult:
    target_infos: list[TargetInfo]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetTargetsResult:
        return cls(
            target_infos=[TargetInfo.from_json(i) for i in data['targetInfos']],
        )


def get_targets(filter: Optional[TargetFilter] = None) -> tuple[T_JSON_DICT, type[GetTargetsResult]]:
    params: T_JSON_DICT = {}
    if filter is not None:
        params['filter'] = filter.to_json()
    cmd: T_JSON_DICT = {"method": "Target.getTargets", "params": params}
    return cmd, GetTargetsResult


def send_message_to_target(message: str, session_id: Optional[SessionID] = None, target_id: Optional[TargetID] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['message'] = message
    if session_id is not None:
        params['sessionId'] = session_id.to_json()
    if target_id is not None:
        params['targetId'] = target_id.to_json()
    cmd: T_JSON_DICT = {"method": "Target.sendMessageToTarget", "params": params}
    return cmd, None


def set_auto_attach(auto_attach: bool, wait_for_debugger_on_start: bool, flatten: Optional[bool] = None, filter: Optional[TargetFilter] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['autoAttach'] = auto_attach
    params['waitForDebuggerOnStart'] = wait_for_debugger_on_start
    if flatten is not None:
        params['flatten'] = flatten
    if filter is not None:
        params['filter'] = filter.to_json()
    cmd: T_JSON_DICT = {"method": "Target.setAutoAttach", "params": params}
    return cmd, None


def auto_attach_related(target_id: TargetID, wait_for_debugger_on_start: bool, filter: Optional[TargetFilter] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['targetId'] = target_id.to_json()
    params['waitForDebuggerOnStart'] = wait_for_debugger_on_start
    if filter is not None:
        params['filter'] = filter.to_json()
    cmd: T_JSON_DICT = {"method": "Target.autoAttachRelated", "params": params}
    return cmd, None


def set_discover_targets(discover: bool, filter: Optional[TargetFilter] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['discover'] = discover
    if filter is not None:
        params['filter'] = filter.to_json()
    cmd: T_JSON_DICT = {"method": "Target.setDiscoverTargets", "params": params}
    return cmd, None


def set_remote_locations(locations: list[RemoteLocation]) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['locations'] = [i.to_json() for i in locations]
    cmd: T_JSON_DICT = {"method": "Target.setRemoteLocations", "params": params}
    return cmd, None


@dataclass
class GetDevToolsTargetResult:
    target_id: Optional[TargetID] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetDevToolsTargetResult:
        return cls(
            target_id=TargetID.from_json(data['targetId']) if 'targetId' in data else None,
        )


def get_dev_tools_target(target_id: TargetID) -> tuple[T_JSON_DICT, type[GetDevToolsTargetResult]]:
    params: T_JSON_DICT = {}
    params['targetId'] = target_id.to_json()
    cmd: T_JSON_DICT = {"method": "Target.getDevToolsTarget", "params": params}
    return cmd, GetDevToolsTargetResult


@dataclass
class OpenDevToolsResult:
    target_id: TargetID

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> OpenDevToolsResult:
        return cls(
            target_id=TargetID.from_json(data['targetId']),
        )


def open_dev_tools(target_id: TargetID, panel_id: Optional[str] = None) -> tuple[T_JSON_DICT, type[OpenDevToolsResult]]:
    params: T_JSON_DICT = {}
    params['targetId'] = target_id.to_json()
    if panel_id is not None:
        params['panelId'] = panel_id
    cmd: T_JSON_DICT = {"method": "Target.openDevTools", "params": params}
    return cmd, OpenDevToolsResult


@dataclass
class AttachedToTarget:
    EVENT_NAME: str = field(init=False, repr=False, default="Target.attachedToTarget")
    session_id: SessionID
    target_info: TargetInfo
    waiting_for_debugger: bool

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> AttachedToTarget:
        return cls(
            session_id=SessionID.from_json(data['sessionId']),
            target_info=TargetInfo.from_json(data['targetInfo']),
            waiting_for_debugger=bool(data['waitingForDebugger']),
        )


@dataclass
class DetachedFromTarget:
    EVENT_NAME: str = field(init=False, repr=False, default="Target.detachedFromTarget")
    session_id: SessionID
    target_id: Optional[TargetID] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DetachedFromTarget:
        return cls(
            session_id=SessionID.from_json(data['sessionId']),
            target_id=TargetID.from_json(data['targetId']) if 'targetId' in data else None,
        )


@dataclass
class ReceivedMessageFromTarget:
    EVENT_NAME: str = field(init=False, repr=False, default="Target.receivedMessageFromTarget")
    session_id: SessionID
    message: str
    target_id: Optional[TargetID] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ReceivedMessageFromTarget:
        return cls(
            session_id=SessionID.from_json(data['sessionId']),
            message=str(data['message']),
            target_id=TargetID.from_json(data['targetId']) if 'targetId' in data else None,
        )


@dataclass
class TargetCreated:
    EVENT_NAME: str = field(init=False, repr=False, default="Target.targetCreated")
    target_info: TargetInfo

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> TargetCreated:
        return cls(
            target_info=TargetInfo.from_json(data['targetInfo']),
        )


@dataclass
class TargetDestroyed:
    EVENT_NAME: str = field(init=False, repr=False, default="Target.targetDestroyed")
    target_id: TargetID

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> TargetDestroyed:
        return cls(
            target_id=TargetID.from_json(data['targetId']),
        )


@dataclass
class TargetCrashed:
    EVENT_NAME: str = field(init=False, repr=False, default="Target.targetCrashed")
    target_id: TargetID
    status: str
    error_code: int

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> TargetCrashed:
        return cls(
            target_id=TargetID.from_json(data['targetId']),
            status=str(data['status']),
            error_code=int(data['errorCode']),
        )


@dataclass
class TargetInfoChanged:
    EVENT_NAME: str = field(init=False, repr=False, default="Target.targetInfoChanged")
    target_info: TargetInfo

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> TargetInfoChanged:
        return cls(
            target_info=TargetInfo.from_json(data['targetInfo']),
        )

