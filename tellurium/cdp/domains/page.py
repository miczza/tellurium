"""Auto-generated CDP bindings for the Page domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from tellurium.cdp.types import T_JSON_DICT


class FrameId(str):
    """CDP string type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> FrameId:
        return cls(val)


class AdFrameType(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> AdFrameType:
        return cls(val)


class AdFrameExplanation(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> AdFrameExplanation:
        return cls(val)


@dataclass
class AdFrameStatus:
    ad_frame_type: AdFrameType
    explanations: Optional[list[AdFrameExplanation]] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['adFrameType'] = ad_frame_type.to_json()
        if self.explanations is not None:
            d['explanations'] = [i.to_json() for i in self.explanations]
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> AdFrameStatus:
        return cls(
            ad_frame_type=AdFrameType.from_json(data['adFrameType']),
            explanations=[AdFrameExplanation.from_json(i) for i in data['explanations']] if 'explanations' in data else None,
        )


class SecureContextType(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> SecureContextType:
        return cls(val)


class CrossOriginIsolatedContextType(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> CrossOriginIsolatedContextType:
        return cls(val)


class GatedAPIFeatures(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> GatedAPIFeatures:
        return cls(val)


class PermissionsPolicyFeature(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> PermissionsPolicyFeature:
        return cls(val)


class PermissionsPolicyBlockReason(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> PermissionsPolicyBlockReason:
        return cls(val)


@dataclass
class PermissionsPolicyBlockLocator:
    frame_id: FrameId
    block_reason: PermissionsPolicyBlockReason

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['frameId'] = frame_id.to_json()
        d['blockReason'] = block_reason.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> PermissionsPolicyBlockLocator:
        return cls(
            frame_id=FrameId.from_json(data['frameId']),
            block_reason=PermissionsPolicyBlockReason.from_json(data['blockReason']),
        )


@dataclass
class PermissionsPolicyFeatureState:
    feature: PermissionsPolicyFeature
    allowed: bool
    locator: Optional[PermissionsPolicyBlockLocator] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['feature'] = feature.to_json()
        d['allowed'] = allowed
        if self.locator is not None:
            d['locator'] = self.locator.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> PermissionsPolicyFeatureState:
        return cls(
            feature=PermissionsPolicyFeature.from_json(data['feature']),
            allowed=bool(data['allowed']),
            locator=PermissionsPolicyBlockLocator.from_json(data['locator']) if 'locator' in data else None,
        )


class OriginTrialTokenStatus(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> OriginTrialTokenStatus:
        return cls(val)


class OriginTrialStatus(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> OriginTrialStatus:
        return cls(val)


class OriginTrialUsageRestriction(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> OriginTrialUsageRestriction:
        return cls(val)


@dataclass
class OriginTrialToken:
    origin: str
    match_sub_domains: bool
    trial_name: str
    expiry_time: TimeSinceEpoch
    is_third_party: bool
    usage_restriction: OriginTrialUsageRestriction

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['origin'] = origin
        d['matchSubDomains'] = match_sub_domains
        d['trialName'] = trial_name
        d['expiryTime'] = expiry_time.to_json()
        d['isThirdParty'] = is_third_party
        d['usageRestriction'] = usage_restriction.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> OriginTrialToken:
        return cls(
            origin=str(data['origin']),
            match_sub_domains=bool(data['matchSubDomains']),
            trial_name=str(data['trialName']),
            expiry_time=TimeSinceEpoch.from_json(data['expiryTime']),
            is_third_party=bool(data['isThirdParty']),
            usage_restriction=OriginTrialUsageRestriction.from_json(data['usageRestriction']),
        )


@dataclass
class OriginTrialTokenWithStatus:
    raw_token_text: str
    status: OriginTrialTokenStatus
    parsed_token: Optional[OriginTrialToken] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['rawTokenText'] = raw_token_text
        d['status'] = status.to_json()
        if self.parsed_token is not None:
            d['parsedToken'] = self.parsed_token.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> OriginTrialTokenWithStatus:
        return cls(
            raw_token_text=str(data['rawTokenText']),
            status=OriginTrialTokenStatus.from_json(data['status']),
            parsed_token=OriginTrialToken.from_json(data['parsedToken']) if 'parsedToken' in data else None,
        )


@dataclass
class OriginTrial:
    trial_name: str
    status: OriginTrialStatus
    tokens_with_status: list[OriginTrialTokenWithStatus]

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['trialName'] = trial_name
        d['status'] = status.to_json()
        d['tokensWithStatus'] = [i.to_json() for i in tokens_with_status]
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> OriginTrial:
        return cls(
            trial_name=str(data['trialName']),
            status=OriginTrialStatus.from_json(data['status']),
            tokens_with_status=[OriginTrialTokenWithStatus.from_json(i) for i in data['tokensWithStatus']],
        )


@dataclass
class SecurityOriginDetails:
    is_localhost: bool

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['isLocalhost'] = is_localhost
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SecurityOriginDetails:
        return cls(
            is_localhost=bool(data['isLocalhost']),
        )


@dataclass
class Frame:
    id: FrameId
    loader_id: LoaderId
    url: str
    domain_and_registry: str
    security_origin: str
    mime_type: str
    secure_context_type: SecureContextType
    cross_origin_isolated_context_type: CrossOriginIsolatedContextType
    gated_api_features: list[GatedAPIFeatures]
    parent_id: Optional[FrameId] = None
    name: Optional[str] = None
    url_fragment: Optional[str] = None
    security_origin_details: Optional[SecurityOriginDetails] = None
    unreachable_url: Optional[str] = None
    ad_frame_status: Optional[AdFrameStatus] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['id'] = id.to_json()
        d['loaderId'] = loader_id.to_json()
        d['url'] = url
        d['domainAndRegistry'] = domain_and_registry
        d['securityOrigin'] = security_origin
        d['mimeType'] = mime_type
        d['secureContextType'] = secure_context_type.to_json()
        d['crossOriginIsolatedContextType'] = cross_origin_isolated_context_type.to_json()
        d['gatedAPIFeatures'] = [i.to_json() for i in gated_api_features]
        if self.parent_id is not None:
            d['parentId'] = self.parent_id.to_json()
        if self.name is not None:
            d['name'] = self.name
        if self.url_fragment is not None:
            d['urlFragment'] = self.url_fragment
        if self.security_origin_details is not None:
            d['securityOriginDetails'] = self.security_origin_details.to_json()
        if self.unreachable_url is not None:
            d['unreachableUrl'] = self.unreachable_url
        if self.ad_frame_status is not None:
            d['adFrameStatus'] = self.ad_frame_status.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> Frame:
        return cls(
            id=FrameId.from_json(data['id']),
            loader_id=LoaderId.from_json(data['loaderId']),
            url=str(data['url']),
            domain_and_registry=str(data['domainAndRegistry']),
            security_origin=str(data['securityOrigin']),
            mime_type=str(data['mimeType']),
            secure_context_type=SecureContextType.from_json(data['secureContextType']),
            cross_origin_isolated_context_type=CrossOriginIsolatedContextType.from_json(data['crossOriginIsolatedContextType']),
            gated_api_features=[GatedAPIFeatures.from_json(i) for i in data['gatedAPIFeatures']],
            parent_id=FrameId.from_json(data['parentId']) if 'parentId' in data else None,
            name=str(data['name']) if 'name' in data else None,
            url_fragment=str(data['urlFragment']) if 'urlFragment' in data else None,
            security_origin_details=SecurityOriginDetails.from_json(data['securityOriginDetails']) if 'securityOriginDetails' in data else None,
            unreachable_url=str(data['unreachableUrl']) if 'unreachableUrl' in data else None,
            ad_frame_status=AdFrameStatus.from_json(data['adFrameStatus']) if 'adFrameStatus' in data else None,
        )


@dataclass
class FrameResource:
    url: str
    type: ResourceType
    mime_type: str
    last_modified: Optional[TimeSinceEpoch] = None
    content_size: Optional[float] = None
    failed: Optional[bool] = None
    canceled: Optional[bool] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['url'] = url
        d['type'] = type.to_json()
        d['mimeType'] = mime_type
        if self.last_modified is not None:
            d['lastModified'] = self.last_modified.to_json()
        if self.content_size is not None:
            d['contentSize'] = self.content_size
        if self.failed is not None:
            d['failed'] = self.failed
        if self.canceled is not None:
            d['canceled'] = self.canceled
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> FrameResource:
        return cls(
            url=str(data['url']),
            type=ResourceType.from_json(data['type']),
            mime_type=str(data['mimeType']),
            last_modified=TimeSinceEpoch.from_json(data['lastModified']) if 'lastModified' in data else None,
            content_size=float(data['contentSize']) if 'contentSize' in data else None,
            failed=bool(data['failed']) if 'failed' in data else None,
            canceled=bool(data['canceled']) if 'canceled' in data else None,
        )


@dataclass
class FrameResourceTree:
    frame: Frame
    resources: list[FrameResource]
    child_frames: Optional[list[FrameResourceTree]] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['frame'] = frame.to_json()
        d['resources'] = [i.to_json() for i in resources]
        if self.child_frames is not None:
            d['childFrames'] = [i.to_json() for i in self.child_frames]
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> FrameResourceTree:
        return cls(
            frame=Frame.from_json(data['frame']),
            resources=[FrameResource.from_json(i) for i in data['resources']],
            child_frames=[FrameResourceTree.from_json(i) for i in data['childFrames']] if 'childFrames' in data else None,
        )


@dataclass
class FrameTree:
    frame: Frame
    child_frames: Optional[list[FrameTree]] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['frame'] = frame.to_json()
        if self.child_frames is not None:
            d['childFrames'] = [i.to_json() for i in self.child_frames]
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> FrameTree:
        return cls(
            frame=Frame.from_json(data['frame']),
            child_frames=[FrameTree.from_json(i) for i in data['childFrames']] if 'childFrames' in data else None,
        )


class ScriptIdentifier(str):
    """CDP string type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> ScriptIdentifier:
        return cls(val)


class TransitionType(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> TransitionType:
        return cls(val)


@dataclass
class NavigationEntry:
    id: int
    url: str
    user_typed_url: str
    title: str
    transition_type: TransitionType

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['id'] = id
        d['url'] = url
        d['userTypedURL'] = user_typed_url
        d['title'] = title
        d['transitionType'] = transition_type.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> NavigationEntry:
        return cls(
            id=int(data['id']),
            url=str(data['url']),
            user_typed_url=str(data['userTypedURL']),
            title=str(data['title']),
            transition_type=TransitionType.from_json(data['transitionType']),
        )


@dataclass
class ScreencastFrameMetadata:
    offset_top: float
    page_scale_factor: float
    device_width: float
    device_height: float
    scroll_offset_x: float
    scroll_offset_y: float
    timestamp: Optional[TimeSinceEpoch] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['offsetTop'] = offset_top
        d['pageScaleFactor'] = page_scale_factor
        d['deviceWidth'] = device_width
        d['deviceHeight'] = device_height
        d['scrollOffsetX'] = scroll_offset_x
        d['scrollOffsetY'] = scroll_offset_y
        if self.timestamp is not None:
            d['timestamp'] = self.timestamp.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ScreencastFrameMetadata:
        return cls(
            offset_top=float(data['offsetTop']),
            page_scale_factor=float(data['pageScaleFactor']),
            device_width=float(data['deviceWidth']),
            device_height=float(data['deviceHeight']),
            scroll_offset_x=float(data['scrollOffsetX']),
            scroll_offset_y=float(data['scrollOffsetY']),
            timestamp=TimeSinceEpoch.from_json(data['timestamp']) if 'timestamp' in data else None,
        )


class DialogType(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> DialogType:
        return cls(val)


@dataclass
class AppManifestError:
    message: str
    critical: int
    line: int
    column: int

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['message'] = message
        d['critical'] = critical
        d['line'] = line
        d['column'] = column
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> AppManifestError:
        return cls(
            message=str(data['message']),
            critical=int(data['critical']),
            line=int(data['line']),
            column=int(data['column']),
        )


@dataclass
class AppManifestParsedProperties:
    scope: str

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['scope'] = scope
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> AppManifestParsedProperties:
        return cls(
            scope=str(data['scope']),
        )


@dataclass
class LayoutViewport:
    page_x: int
    page_y: int
    client_width: int
    client_height: int

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['pageX'] = page_x
        d['pageY'] = page_y
        d['clientWidth'] = client_width
        d['clientHeight'] = client_height
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> LayoutViewport:
        return cls(
            page_x=int(data['pageX']),
            page_y=int(data['pageY']),
            client_width=int(data['clientWidth']),
            client_height=int(data['clientHeight']),
        )


@dataclass
class VisualViewport:
    offset_x: float
    offset_y: float
    page_x: float
    page_y: float
    client_width: float
    client_height: float
    scale: float
    zoom: Optional[float] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['offsetX'] = offset_x
        d['offsetY'] = offset_y
        d['pageX'] = page_x
        d['pageY'] = page_y
        d['clientWidth'] = client_width
        d['clientHeight'] = client_height
        d['scale'] = scale
        if self.zoom is not None:
            d['zoom'] = self.zoom
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> VisualViewport:
        return cls(
            offset_x=float(data['offsetX']),
            offset_y=float(data['offsetY']),
            page_x=float(data['pageX']),
            page_y=float(data['pageY']),
            client_width=float(data['clientWidth']),
            client_height=float(data['clientHeight']),
            scale=float(data['scale']),
            zoom=float(data['zoom']) if 'zoom' in data else None,
        )


@dataclass
class Viewport:
    x: float
    y: float
    width: float
    height: float
    scale: float

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['x'] = x
        d['y'] = y
        d['width'] = width
        d['height'] = height
        d['scale'] = scale
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> Viewport:
        return cls(
            x=float(data['x']),
            y=float(data['y']),
            width=float(data['width']),
            height=float(data['height']),
            scale=float(data['scale']),
        )


@dataclass
class FontFamilies:
    standard: Optional[str] = None
    fixed: Optional[str] = None
    serif: Optional[str] = None
    sans_serif: Optional[str] = None
    cursive: Optional[str] = None
    fantasy: Optional[str] = None
    math: Optional[str] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        if self.standard is not None:
            d['standard'] = self.standard
        if self.fixed is not None:
            d['fixed'] = self.fixed
        if self.serif is not None:
            d['serif'] = self.serif
        if self.sans_serif is not None:
            d['sansSerif'] = self.sans_serif
        if self.cursive is not None:
            d['cursive'] = self.cursive
        if self.fantasy is not None:
            d['fantasy'] = self.fantasy
        if self.math is not None:
            d['math'] = self.math
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> FontFamilies:
        return cls(
            standard=str(data['standard']) if 'standard' in data else None,
            fixed=str(data['fixed']) if 'fixed' in data else None,
            serif=str(data['serif']) if 'serif' in data else None,
            sans_serif=str(data['sansSerif']) if 'sansSerif' in data else None,
            cursive=str(data['cursive']) if 'cursive' in data else None,
            fantasy=str(data['fantasy']) if 'fantasy' in data else None,
            math=str(data['math']) if 'math' in data else None,
        )


@dataclass
class ScriptFontFamilies:
    script: str
    font_families: FontFamilies

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['script'] = script
        d['fontFamilies'] = font_families.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ScriptFontFamilies:
        return cls(
            script=str(data['script']),
            font_families=FontFamilies.from_json(data['fontFamilies']),
        )


@dataclass
class FontSizes:
    standard: Optional[int] = None
    fixed: Optional[int] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        if self.standard is not None:
            d['standard'] = self.standard
        if self.fixed is not None:
            d['fixed'] = self.fixed
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> FontSizes:
        return cls(
            standard=int(data['standard']) if 'standard' in data else None,
            fixed=int(data['fixed']) if 'fixed' in data else None,
        )


class ClientNavigationReason(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> ClientNavigationReason:
        return cls(val)


class ClientNavigationDisposition(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> ClientNavigationDisposition:
        return cls(val)


@dataclass
class InstallabilityErrorArgument:
    name: str
    value: str

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['name'] = name
        d['value'] = value
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> InstallabilityErrorArgument:
        return cls(
            name=str(data['name']),
            value=str(data['value']),
        )


@dataclass
class InstallabilityError:
    error_id: str
    error_arguments: list[InstallabilityErrorArgument]

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['errorId'] = error_id
        d['errorArguments'] = [i.to_json() for i in error_arguments]
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> InstallabilityError:
        return cls(
            error_id=str(data['errorId']),
            error_arguments=[InstallabilityErrorArgument.from_json(i) for i in data['errorArguments']],
        )


class ReferrerPolicy(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> ReferrerPolicy:
        return cls(val)


@dataclass
class CompilationCacheParams:
    url: str
    eager: Optional[bool] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['url'] = url
        if self.eager is not None:
            d['eager'] = self.eager
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CompilationCacheParams:
        return cls(
            url=str(data['url']),
            eager=bool(data['eager']) if 'eager' in data else None,
        )


@dataclass
class FileFilter:
    name: Optional[str] = None
    accepts: Optional[list[str]] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        if self.name is not None:
            d['name'] = self.name
        if self.accepts is not None:
            d['accepts'] = list(self.accepts)
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> FileFilter:
        return cls(
            name=str(data['name']) if 'name' in data else None,
            accepts=[str(i) for i in data['accepts']] if 'accepts' in data else None,
        )


@dataclass
class FileHandler:
    action: str
    name: str
    launch_type: str
    icons: Optional[list[ImageResource]] = None
    accepts: Optional[list[FileFilter]] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['action'] = action
        d['name'] = name
        d['launchType'] = launch_type
        if self.icons is not None:
            d['icons'] = [i.to_json() for i in self.icons]
        if self.accepts is not None:
            d['accepts'] = [i.to_json() for i in self.accepts]
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> FileHandler:
        return cls(
            action=str(data['action']),
            name=str(data['name']),
            launch_type=str(data['launchType']),
            icons=[ImageResource.from_json(i) for i in data['icons']] if 'icons' in data else None,
            accepts=[FileFilter.from_json(i) for i in data['accepts']] if 'accepts' in data else None,
        )


@dataclass
class ImageResource:
    url: str
    sizes: Optional[str] = None
    type: Optional[str] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['url'] = url
        if self.sizes is not None:
            d['sizes'] = self.sizes
        if self.type is not None:
            d['type'] = self.type
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ImageResource:
        return cls(
            url=str(data['url']),
            sizes=str(data['sizes']) if 'sizes' in data else None,
            type=str(data['type']) if 'type' in data else None,
        )


@dataclass
class LaunchHandler:
    client_mode: str

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['clientMode'] = client_mode
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> LaunchHandler:
        return cls(
            client_mode=str(data['clientMode']),
        )


@dataclass
class ProtocolHandler:
    protocol: str
    url: str

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['protocol'] = protocol
        d['url'] = url
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ProtocolHandler:
        return cls(
            protocol=str(data['protocol']),
            url=str(data['url']),
        )


@dataclass
class RelatedApplication:
    url: str
    id: Optional[str] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['url'] = url
        if self.id is not None:
            d['id'] = self.id
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> RelatedApplication:
        return cls(
            url=str(data['url']),
            id=str(data['id']) if 'id' in data else None,
        )


@dataclass
class ScopeExtension:
    origin: str
    has_origin_wildcard: bool

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['origin'] = origin
        d['hasOriginWildcard'] = has_origin_wildcard
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ScopeExtension:
        return cls(
            origin=str(data['origin']),
            has_origin_wildcard=bool(data['hasOriginWildcard']),
        )


@dataclass
class Screenshot:
    image: ImageResource
    form_factor: str
    label: Optional[str] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['image'] = image.to_json()
        d['formFactor'] = form_factor
        if self.label is not None:
            d['label'] = self.label
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> Screenshot:
        return cls(
            image=ImageResource.from_json(data['image']),
            form_factor=str(data['formFactor']),
            label=str(data['label']) if 'label' in data else None,
        )


@dataclass
class ShareTarget:
    action: str
    method: str
    enctype: str
    title: Optional[str] = None
    text: Optional[str] = None
    url: Optional[str] = None
    files: Optional[list[FileFilter]] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['action'] = action
        d['method'] = method
        d['enctype'] = enctype
        if self.title is not None:
            d['title'] = self.title
        if self.text is not None:
            d['text'] = self.text
        if self.url is not None:
            d['url'] = self.url
        if self.files is not None:
            d['files'] = [i.to_json() for i in self.files]
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ShareTarget:
        return cls(
            action=str(data['action']),
            method=str(data['method']),
            enctype=str(data['enctype']),
            title=str(data['title']) if 'title' in data else None,
            text=str(data['text']) if 'text' in data else None,
            url=str(data['url']) if 'url' in data else None,
            files=[FileFilter.from_json(i) for i in data['files']] if 'files' in data else None,
        )


@dataclass
class Shortcut:
    name: str
    url: str

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['name'] = name
        d['url'] = url
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> Shortcut:
        return cls(
            name=str(data['name']),
            url=str(data['url']),
        )


@dataclass
class WebAppManifest:
    background_color: Optional[str] = None
    description: Optional[str] = None
    dir: Optional[str] = None
    display: Optional[str] = None
    display_overrides: Optional[list[str]] = None
    file_handlers: Optional[list[FileHandler]] = None
    icons: Optional[list[ImageResource]] = None
    id: Optional[str] = None
    lang: Optional[str] = None
    launch_handler: Optional[LaunchHandler] = None
    name: Optional[str] = None
    orientation: Optional[str] = None
    prefer_related_applications: Optional[bool] = None
    protocol_handlers: Optional[list[ProtocolHandler]] = None
    related_applications: Optional[list[RelatedApplication]] = None
    scope: Optional[str] = None
    scope_extensions: Optional[list[ScopeExtension]] = None
    screenshots: Optional[list[Screenshot]] = None
    share_target: Optional[ShareTarget] = None
    short_name: Optional[str] = None
    shortcuts: Optional[list[Shortcut]] = None
    start_url: Optional[str] = None
    theme_color: Optional[str] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        if self.background_color is not None:
            d['backgroundColor'] = self.background_color
        if self.description is not None:
            d['description'] = self.description
        if self.dir is not None:
            d['dir'] = self.dir
        if self.display is not None:
            d['display'] = self.display
        if self.display_overrides is not None:
            d['displayOverrides'] = list(self.display_overrides)
        if self.file_handlers is not None:
            d['fileHandlers'] = [i.to_json() for i in self.file_handlers]
        if self.icons is not None:
            d['icons'] = [i.to_json() for i in self.icons]
        if self.id is not None:
            d['id'] = self.id
        if self.lang is not None:
            d['lang'] = self.lang
        if self.launch_handler is not None:
            d['launchHandler'] = self.launch_handler.to_json()
        if self.name is not None:
            d['name'] = self.name
        if self.orientation is not None:
            d['orientation'] = self.orientation
        if self.prefer_related_applications is not None:
            d['preferRelatedApplications'] = self.prefer_related_applications
        if self.protocol_handlers is not None:
            d['protocolHandlers'] = [i.to_json() for i in self.protocol_handlers]
        if self.related_applications is not None:
            d['relatedApplications'] = [i.to_json() for i in self.related_applications]
        if self.scope is not None:
            d['scope'] = self.scope
        if self.scope_extensions is not None:
            d['scopeExtensions'] = [i.to_json() for i in self.scope_extensions]
        if self.screenshots is not None:
            d['screenshots'] = [i.to_json() for i in self.screenshots]
        if self.share_target is not None:
            d['shareTarget'] = self.share_target.to_json()
        if self.short_name is not None:
            d['shortName'] = self.short_name
        if self.shortcuts is not None:
            d['shortcuts'] = [i.to_json() for i in self.shortcuts]
        if self.start_url is not None:
            d['startUrl'] = self.start_url
        if self.theme_color is not None:
            d['themeColor'] = self.theme_color
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> WebAppManifest:
        return cls(
            background_color=str(data['backgroundColor']) if 'backgroundColor' in data else None,
            description=str(data['description']) if 'description' in data else None,
            dir=str(data['dir']) if 'dir' in data else None,
            display=str(data['display']) if 'display' in data else None,
            display_overrides=[str(i) for i in data['displayOverrides']] if 'displayOverrides' in data else None,
            file_handlers=[FileHandler.from_json(i) for i in data['fileHandlers']] if 'fileHandlers' in data else None,
            icons=[ImageResource.from_json(i) for i in data['icons']] if 'icons' in data else None,
            id=str(data['id']) if 'id' in data else None,
            lang=str(data['lang']) if 'lang' in data else None,
            launch_handler=LaunchHandler.from_json(data['launchHandler']) if 'launchHandler' in data else None,
            name=str(data['name']) if 'name' in data else None,
            orientation=str(data['orientation']) if 'orientation' in data else None,
            prefer_related_applications=bool(data['preferRelatedApplications']) if 'preferRelatedApplications' in data else None,
            protocol_handlers=[ProtocolHandler.from_json(i) for i in data['protocolHandlers']] if 'protocolHandlers' in data else None,
            related_applications=[RelatedApplication.from_json(i) for i in data['relatedApplications']] if 'relatedApplications' in data else None,
            scope=str(data['scope']) if 'scope' in data else None,
            scope_extensions=[ScopeExtension.from_json(i) for i in data['scopeExtensions']] if 'scopeExtensions' in data else None,
            screenshots=[Screenshot.from_json(i) for i in data['screenshots']] if 'screenshots' in data else None,
            share_target=ShareTarget.from_json(data['shareTarget']) if 'shareTarget' in data else None,
            short_name=str(data['shortName']) if 'shortName' in data else None,
            shortcuts=[Shortcut.from_json(i) for i in data['shortcuts']] if 'shortcuts' in data else None,
            start_url=str(data['startUrl']) if 'startUrl' in data else None,
            theme_color=str(data['themeColor']) if 'themeColor' in data else None,
        )


class NavigationType(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> NavigationType:
        return cls(val)


class BackForwardCacheNotRestoredReason(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> BackForwardCacheNotRestoredReason:
        return cls(val)


class BackForwardCacheNotRestoredReasonType(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> BackForwardCacheNotRestoredReasonType:
        return cls(val)


@dataclass
class BackForwardCacheBlockingDetails:
    line_number: int
    column_number: int
    url: Optional[str] = None
    function: Optional[str] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['lineNumber'] = line_number
        d['columnNumber'] = column_number
        if self.url is not None:
            d['url'] = self.url
        if self.function is not None:
            d['function'] = self.function
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> BackForwardCacheBlockingDetails:
        return cls(
            line_number=int(data['lineNumber']),
            column_number=int(data['columnNumber']),
            url=str(data['url']) if 'url' in data else None,
            function=str(data['function']) if 'function' in data else None,
        )


@dataclass
class BackForwardCacheNotRestoredExplanation:
    type: BackForwardCacheNotRestoredReasonType
    reason: BackForwardCacheNotRestoredReason
    context: Optional[str] = None
    details: Optional[list[BackForwardCacheBlockingDetails]] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['type'] = type.to_json()
        d['reason'] = reason.to_json()
        if self.context is not None:
            d['context'] = self.context
        if self.details is not None:
            d['details'] = [i.to_json() for i in self.details]
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> BackForwardCacheNotRestoredExplanation:
        return cls(
            type=BackForwardCacheNotRestoredReasonType.from_json(data['type']),
            reason=BackForwardCacheNotRestoredReason.from_json(data['reason']),
            context=str(data['context']) if 'context' in data else None,
            details=[BackForwardCacheBlockingDetails.from_json(i) for i in data['details']] if 'details' in data else None,
        )


@dataclass
class BackForwardCacheNotRestoredExplanationTree:
    url: str
    explanations: list[BackForwardCacheNotRestoredExplanation]
    children: list[BackForwardCacheNotRestoredExplanationTree]

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['url'] = url
        d['explanations'] = [i.to_json() for i in explanations]
        d['children'] = [i.to_json() for i in children]
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> BackForwardCacheNotRestoredExplanationTree:
        return cls(
            url=str(data['url']),
            explanations=[BackForwardCacheNotRestoredExplanation.from_json(i) for i in data['explanations']],
            children=[BackForwardCacheNotRestoredExplanationTree.from_json(i) for i in data['children']],
        )


@dataclass
class AddScriptToEvaluateOnLoadResult:
    identifier: ScriptIdentifier

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> AddScriptToEvaluateOnLoadResult:
        return cls(
            identifier=ScriptIdentifier.from_json(data['identifier']),
        )


def add_script_to_evaluate_on_load(script_source: str) -> tuple[T_JSON_DICT, type[AddScriptToEvaluateOnLoadResult]]:
    params: T_JSON_DICT = {}
    params['scriptSource'] = script_source
    cmd: T_JSON_DICT = {"method": "Page.addScriptToEvaluateOnLoad", "params": params}
    return cmd, AddScriptToEvaluateOnLoadResult


@dataclass
class AddScriptToEvaluateOnNewDocumentResult:
    identifier: ScriptIdentifier

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> AddScriptToEvaluateOnNewDocumentResult:
        return cls(
            identifier=ScriptIdentifier.from_json(data['identifier']),
        )


def add_script_to_evaluate_on_new_document(source: str, world_name: Optional[str] = None, include_command_line_api: Optional[bool] = None, run_immediately: Optional[bool] = None) -> tuple[T_JSON_DICT, type[AddScriptToEvaluateOnNewDocumentResult]]:
    params: T_JSON_DICT = {}
    params['source'] = source
    if world_name is not None:
        params['worldName'] = world_name
    if include_command_line_api is not None:
        params['includeCommandLineAPI'] = include_command_line_api
    if run_immediately is not None:
        params['runImmediately'] = run_immediately
    cmd: T_JSON_DICT = {"method": "Page.addScriptToEvaluateOnNewDocument", "params": params}
    return cmd, AddScriptToEvaluateOnNewDocumentResult


def bring_to_front() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Page.bringToFront", "params": params}
    return cmd, None


@dataclass
class CaptureScreenshotResult:
    data: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CaptureScreenshotResult:
        return cls(
            data=str(data['data']),
        )


def capture_screenshot(format: Optional[str] = None, quality: Optional[int] = None, clip: Optional[Viewport] = None, from_surface: Optional[bool] = None, capture_beyond_viewport: Optional[bool] = None, optimize_for_speed: Optional[bool] = None) -> tuple[T_JSON_DICT, type[CaptureScreenshotResult]]:
    params: T_JSON_DICT = {}
    if format is not None:
        params['format'] = format
    if quality is not None:
        params['quality'] = quality
    if clip is not None:
        params['clip'] = clip.to_json()
    if from_surface is not None:
        params['fromSurface'] = from_surface
    if capture_beyond_viewport is not None:
        params['captureBeyondViewport'] = capture_beyond_viewport
    if optimize_for_speed is not None:
        params['optimizeForSpeed'] = optimize_for_speed
    cmd: T_JSON_DICT = {"method": "Page.captureScreenshot", "params": params}
    return cmd, CaptureScreenshotResult


@dataclass
class CaptureSnapshotResult:
    data: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CaptureSnapshotResult:
        return cls(
            data=str(data['data']),
        )


def capture_snapshot(format: Optional[str] = None) -> tuple[T_JSON_DICT, type[CaptureSnapshotResult]]:
    params: T_JSON_DICT = {}
    if format is not None:
        params['format'] = format
    cmd: T_JSON_DICT = {"method": "Page.captureSnapshot", "params": params}
    return cmd, CaptureSnapshotResult


def clear_device_metrics_override() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Page.clearDeviceMetricsOverride", "params": params}
    return cmd, None


def clear_device_orientation_override() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Page.clearDeviceOrientationOverride", "params": params}
    return cmd, None


def clear_geolocation_override() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Page.clearGeolocationOverride", "params": params}
    return cmd, None


@dataclass
class CreateIsolatedWorldResult:
    execution_context_id: ExecutionContextId

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CreateIsolatedWorldResult:
        return cls(
            execution_context_id=ExecutionContextId.from_json(data['executionContextId']),
        )


def create_isolated_world(frame_id: FrameId, world_name: Optional[str] = None, grant_univeral_access: Optional[bool] = None) -> tuple[T_JSON_DICT, type[CreateIsolatedWorldResult]]:
    params: T_JSON_DICT = {}
    params['frameId'] = frame_id.to_json()
    if world_name is not None:
        params['worldName'] = world_name
    if grant_univeral_access is not None:
        params['grantUniveralAccess'] = grant_univeral_access
    cmd: T_JSON_DICT = {"method": "Page.createIsolatedWorld", "params": params}
    return cmd, CreateIsolatedWorldResult


def delete_cookie(cookie_name: str, url: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['cookieName'] = cookie_name
    params['url'] = url
    cmd: T_JSON_DICT = {"method": "Page.deleteCookie", "params": params}
    return cmd, None


def disable() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Page.disable", "params": params}
    return cmd, None


def enable(enable_file_chooser_opened_event: Optional[bool] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    if enable_file_chooser_opened_event is not None:
        params['enableFileChooserOpenedEvent'] = enable_file_chooser_opened_event
    cmd: T_JSON_DICT = {"method": "Page.enable", "params": params}
    return cmd, None


@dataclass
class GetAppManifestResult:
    url: str
    errors: list[AppManifestError]
    manifest: WebAppManifest
    data: Optional[str] = None
    parsed: Optional[AppManifestParsedProperties] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetAppManifestResult:
        return cls(
            url=str(data['url']),
            errors=[AppManifestError.from_json(i) for i in data['errors']],
            manifest=WebAppManifest.from_json(data['manifest']),
            data=str(data['data']) if 'data' in data else None,
            parsed=AppManifestParsedProperties.from_json(data['parsed']) if 'parsed' in data else None,
        )


def get_app_manifest(manifest_id: Optional[str] = None) -> tuple[T_JSON_DICT, type[GetAppManifestResult]]:
    params: T_JSON_DICT = {}
    if manifest_id is not None:
        params['manifestId'] = manifest_id
    cmd: T_JSON_DICT = {"method": "Page.getAppManifest", "params": params}
    return cmd, GetAppManifestResult


@dataclass
class GetInstallabilityErrorsResult:
    installability_errors: list[InstallabilityError]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetInstallabilityErrorsResult:
        return cls(
            installability_errors=[InstallabilityError.from_json(i) for i in data['installabilityErrors']],
        )


def get_installability_errors() -> tuple[T_JSON_DICT, type[GetInstallabilityErrorsResult]]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Page.getInstallabilityErrors", "params": params}
    return cmd, GetInstallabilityErrorsResult


@dataclass
class GetManifestIconsResult:
    primary_icon: Optional[str] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetManifestIconsResult:
        return cls(
            primary_icon=str(data['primaryIcon']) if 'primaryIcon' in data else None,
        )


def get_manifest_icons() -> tuple[T_JSON_DICT, type[GetManifestIconsResult]]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Page.getManifestIcons", "params": params}
    return cmd, GetManifestIconsResult


@dataclass
class GetAppIdResult:
    app_id: Optional[str] = None
    recommended_id: Optional[str] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetAppIdResult:
        return cls(
            app_id=str(data['appId']) if 'appId' in data else None,
            recommended_id=str(data['recommendedId']) if 'recommendedId' in data else None,
        )


def get_app_id() -> tuple[T_JSON_DICT, type[GetAppIdResult]]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Page.getAppId", "params": params}
    return cmd, GetAppIdResult


@dataclass
class GetAdScriptAncestryResult:
    ad_script_ancestry: Optional[AdAncestry] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetAdScriptAncestryResult:
        return cls(
            ad_script_ancestry=AdAncestry.from_json(data['adScriptAncestry']) if 'adScriptAncestry' in data else None,
        )


def get_ad_script_ancestry(frame_id: FrameId) -> tuple[T_JSON_DICT, type[GetAdScriptAncestryResult]]:
    params: T_JSON_DICT = {}
    params['frameId'] = frame_id.to_json()
    cmd: T_JSON_DICT = {"method": "Page.getAdScriptAncestry", "params": params}
    return cmd, GetAdScriptAncestryResult


@dataclass
class GetFrameTreeResult:
    frame_tree: FrameTree

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetFrameTreeResult:
        return cls(
            frame_tree=FrameTree.from_json(data['frameTree']),
        )


def get_frame_tree() -> tuple[T_JSON_DICT, type[GetFrameTreeResult]]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Page.getFrameTree", "params": params}
    return cmd, GetFrameTreeResult


@dataclass
class GetLayoutMetricsResult:
    layout_viewport: LayoutViewport
    visual_viewport: VisualViewport
    content_size: Rect
    css_layout_viewport: LayoutViewport
    css_visual_viewport: VisualViewport
    css_content_size: Rect

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetLayoutMetricsResult:
        return cls(
            layout_viewport=LayoutViewport.from_json(data['layoutViewport']),
            visual_viewport=VisualViewport.from_json(data['visualViewport']),
            content_size=Rect.from_json(data['contentSize']),
            css_layout_viewport=LayoutViewport.from_json(data['cssLayoutViewport']),
            css_visual_viewport=VisualViewport.from_json(data['cssVisualViewport']),
            css_content_size=Rect.from_json(data['cssContentSize']),
        )


def get_layout_metrics() -> tuple[T_JSON_DICT, type[GetLayoutMetricsResult]]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Page.getLayoutMetrics", "params": params}
    return cmd, GetLayoutMetricsResult


@dataclass
class GetNavigationHistoryResult:
    current_index: int
    entries: list[NavigationEntry]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetNavigationHistoryResult:
        return cls(
            current_index=int(data['currentIndex']),
            entries=[NavigationEntry.from_json(i) for i in data['entries']],
        )


def get_navigation_history() -> tuple[T_JSON_DICT, type[GetNavigationHistoryResult]]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Page.getNavigationHistory", "params": params}
    return cmd, GetNavigationHistoryResult


def reset_navigation_history() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Page.resetNavigationHistory", "params": params}
    return cmd, None


@dataclass
class GetResourceContentResult:
    content: str
    base64_encoded: bool

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetResourceContentResult:
        return cls(
            content=str(data['content']),
            base64_encoded=bool(data['base64Encoded']),
        )


def get_resource_content(frame_id: FrameId, url: str) -> tuple[T_JSON_DICT, type[GetResourceContentResult]]:
    params: T_JSON_DICT = {}
    params['frameId'] = frame_id.to_json()
    params['url'] = url
    cmd: T_JSON_DICT = {"method": "Page.getResourceContent", "params": params}
    return cmd, GetResourceContentResult


@dataclass
class GetResourceTreeResult:
    frame_tree: FrameResourceTree

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetResourceTreeResult:
        return cls(
            frame_tree=FrameResourceTree.from_json(data['frameTree']),
        )


def get_resource_tree() -> tuple[T_JSON_DICT, type[GetResourceTreeResult]]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Page.getResourceTree", "params": params}
    return cmd, GetResourceTreeResult


def handle_java_script_dialog(accept: bool, prompt_text: Optional[str] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['accept'] = accept
    if prompt_text is not None:
        params['promptText'] = prompt_text
    cmd: T_JSON_DICT = {"method": "Page.handleJavaScriptDialog", "params": params}
    return cmd, None


@dataclass
class NavigateResult:
    frame_id: FrameId
    loader_id: Optional[LoaderId] = None
    error_text: Optional[str] = None
    is_download: Optional[bool] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> NavigateResult:
        return cls(
            frame_id=FrameId.from_json(data['frameId']),
            loader_id=LoaderId.from_json(data['loaderId']) if 'loaderId' in data else None,
            error_text=str(data['errorText']) if 'errorText' in data else None,
            is_download=bool(data['isDownload']) if 'isDownload' in data else None,
        )


def navigate(url: str, referrer: Optional[str] = None, transition_type: Optional[TransitionType] = None, frame_id: Optional[FrameId] = None, referrer_policy: Optional[ReferrerPolicy] = None) -> tuple[T_JSON_DICT, type[NavigateResult]]:
    params: T_JSON_DICT = {}
    params['url'] = url
    if referrer is not None:
        params['referrer'] = referrer
    if transition_type is not None:
        params['transitionType'] = transition_type.to_json()
    if frame_id is not None:
        params['frameId'] = frame_id.to_json()
    if referrer_policy is not None:
        params['referrerPolicy'] = referrer_policy.to_json()
    cmd: T_JSON_DICT = {"method": "Page.navigate", "params": params}
    return cmd, NavigateResult


def navigate_to_history_entry(entry_id: int) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['entryId'] = entry_id
    cmd: T_JSON_DICT = {"method": "Page.navigateToHistoryEntry", "params": params}
    return cmd, None


@dataclass
class PrintToPDFResult:
    data: str
    stream: Optional[StreamHandle] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> PrintToPDFResult:
        return cls(
            data=str(data['data']),
            stream=StreamHandle.from_json(data['stream']) if 'stream' in data else None,
        )


def print_to_pdf(landscape: Optional[bool] = None, display_header_footer: Optional[bool] = None, print_background: Optional[bool] = None, scale: Optional[float] = None, paper_width: Optional[float] = None, paper_height: Optional[float] = None, margin_top: Optional[float] = None, margin_bottom: Optional[float] = None, margin_left: Optional[float] = None, margin_right: Optional[float] = None, page_ranges: Optional[str] = None, header_template: Optional[str] = None, footer_template: Optional[str] = None, prefer_css_page_size: Optional[bool] = None, transfer_mode: Optional[str] = None, generate_tagged_pdf: Optional[bool] = None, generate_document_outline: Optional[bool] = None) -> tuple[T_JSON_DICT, type[PrintToPDFResult]]:
    params: T_JSON_DICT = {}
    if landscape is not None:
        params['landscape'] = landscape
    if display_header_footer is not None:
        params['displayHeaderFooter'] = display_header_footer
    if print_background is not None:
        params['printBackground'] = print_background
    if scale is not None:
        params['scale'] = scale
    if paper_width is not None:
        params['paperWidth'] = paper_width
    if paper_height is not None:
        params['paperHeight'] = paper_height
    if margin_top is not None:
        params['marginTop'] = margin_top
    if margin_bottom is not None:
        params['marginBottom'] = margin_bottom
    if margin_left is not None:
        params['marginLeft'] = margin_left
    if margin_right is not None:
        params['marginRight'] = margin_right
    if page_ranges is not None:
        params['pageRanges'] = page_ranges
    if header_template is not None:
        params['headerTemplate'] = header_template
    if footer_template is not None:
        params['footerTemplate'] = footer_template
    if prefer_css_page_size is not None:
        params['preferCSSPageSize'] = prefer_css_page_size
    if transfer_mode is not None:
        params['transferMode'] = transfer_mode
    if generate_tagged_pdf is not None:
        params['generateTaggedPDF'] = generate_tagged_pdf
    if generate_document_outline is not None:
        params['generateDocumentOutline'] = generate_document_outline
    cmd: T_JSON_DICT = {"method": "Page.printToPDF", "params": params}
    return cmd, PrintToPDFResult


def reload(ignore_cache: Optional[bool] = None, script_to_evaluate_on_load: Optional[str] = None, loader_id: Optional[LoaderId] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    if ignore_cache is not None:
        params['ignoreCache'] = ignore_cache
    if script_to_evaluate_on_load is not None:
        params['scriptToEvaluateOnLoad'] = script_to_evaluate_on_load
    if loader_id is not None:
        params['loaderId'] = loader_id.to_json()
    cmd: T_JSON_DICT = {"method": "Page.reload", "params": params}
    return cmd, None


def remove_script_to_evaluate_on_load(identifier: ScriptIdentifier) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['identifier'] = identifier.to_json()
    cmd: T_JSON_DICT = {"method": "Page.removeScriptToEvaluateOnLoad", "params": params}
    return cmd, None


def remove_script_to_evaluate_on_new_document(identifier: ScriptIdentifier) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['identifier'] = identifier.to_json()
    cmd: T_JSON_DICT = {"method": "Page.removeScriptToEvaluateOnNewDocument", "params": params}
    return cmd, None


def screencast_frame_ack(session_id: int) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['sessionId'] = session_id
    cmd: T_JSON_DICT = {"method": "Page.screencastFrameAck", "params": params}
    return cmd, None


@dataclass
class SearchInResourceResult:
    result: list[SearchMatch]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SearchInResourceResult:
        return cls(
            result=[SearchMatch.from_json(i) for i in data['result']],
        )


def search_in_resource(frame_id: FrameId, url: str, query: str, case_sensitive: Optional[bool] = None, is_regex: Optional[bool] = None) -> tuple[T_JSON_DICT, type[SearchInResourceResult]]:
    params: T_JSON_DICT = {}
    params['frameId'] = frame_id.to_json()
    params['url'] = url
    params['query'] = query
    if case_sensitive is not None:
        params['caseSensitive'] = case_sensitive
    if is_regex is not None:
        params['isRegex'] = is_regex
    cmd: T_JSON_DICT = {"method": "Page.searchInResource", "params": params}
    return cmd, SearchInResourceResult


def set_ad_blocking_enabled(enabled: bool) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['enabled'] = enabled
    cmd: T_JSON_DICT = {"method": "Page.setAdBlockingEnabled", "params": params}
    return cmd, None


def set_bypass_csp(enabled: bool) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['enabled'] = enabled
    cmd: T_JSON_DICT = {"method": "Page.setBypassCSP", "params": params}
    return cmd, None


@dataclass
class GetPermissionsPolicyStateResult:
    states: list[PermissionsPolicyFeatureState]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetPermissionsPolicyStateResult:
        return cls(
            states=[PermissionsPolicyFeatureState.from_json(i) for i in data['states']],
        )


def get_permissions_policy_state(frame_id: FrameId) -> tuple[T_JSON_DICT, type[GetPermissionsPolicyStateResult]]:
    params: T_JSON_DICT = {}
    params['frameId'] = frame_id.to_json()
    cmd: T_JSON_DICT = {"method": "Page.getPermissionsPolicyState", "params": params}
    return cmd, GetPermissionsPolicyStateResult


@dataclass
class GetOriginTrialsResult:
    origin_trials: list[OriginTrial]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetOriginTrialsResult:
        return cls(
            origin_trials=[OriginTrial.from_json(i) for i in data['originTrials']],
        )


def get_origin_trials(frame_id: FrameId) -> tuple[T_JSON_DICT, type[GetOriginTrialsResult]]:
    params: T_JSON_DICT = {}
    params['frameId'] = frame_id.to_json()
    cmd: T_JSON_DICT = {"method": "Page.getOriginTrials", "params": params}
    return cmd, GetOriginTrialsResult


def set_device_metrics_override(width: int, height: int, device_scale_factor: float, mobile: bool, scale: Optional[float] = None, screen_width: Optional[int] = None, screen_height: Optional[int] = None, position_x: Optional[int] = None, position_y: Optional[int] = None, dont_set_visible_size: Optional[bool] = None, screen_orientation: Optional[ScreenOrientation] = None, viewport: Optional[Viewport] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['width'] = width
    params['height'] = height
    params['deviceScaleFactor'] = device_scale_factor
    params['mobile'] = mobile
    if scale is not None:
        params['scale'] = scale
    if screen_width is not None:
        params['screenWidth'] = screen_width
    if screen_height is not None:
        params['screenHeight'] = screen_height
    if position_x is not None:
        params['positionX'] = position_x
    if position_y is not None:
        params['positionY'] = position_y
    if dont_set_visible_size is not None:
        params['dontSetVisibleSize'] = dont_set_visible_size
    if screen_orientation is not None:
        params['screenOrientation'] = screen_orientation.to_json()
    if viewport is not None:
        params['viewport'] = viewport.to_json()
    cmd: T_JSON_DICT = {"method": "Page.setDeviceMetricsOverride", "params": params}
    return cmd, None


def set_device_orientation_override(alpha: float, beta: float, gamma: float) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['alpha'] = alpha
    params['beta'] = beta
    params['gamma'] = gamma
    cmd: T_JSON_DICT = {"method": "Page.setDeviceOrientationOverride", "params": params}
    return cmd, None


def set_font_families(font_families: FontFamilies, for_scripts: Optional[list[ScriptFontFamilies]] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['fontFamilies'] = font_families.to_json()
    if for_scripts is not None:
        params['forScripts'] = [i.to_json() for i in for_scripts]
    cmd: T_JSON_DICT = {"method": "Page.setFontFamilies", "params": params}
    return cmd, None


def set_font_sizes(font_sizes: FontSizes) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['fontSizes'] = font_sizes.to_json()
    cmd: T_JSON_DICT = {"method": "Page.setFontSizes", "params": params}
    return cmd, None


def set_document_content(frame_id: FrameId, html: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['frameId'] = frame_id.to_json()
    params['html'] = html
    cmd: T_JSON_DICT = {"method": "Page.setDocumentContent", "params": params}
    return cmd, None


def set_download_behavior(behavior: str, download_path: Optional[str] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['behavior'] = behavior
    if download_path is not None:
        params['downloadPath'] = download_path
    cmd: T_JSON_DICT = {"method": "Page.setDownloadBehavior", "params": params}
    return cmd, None


def set_geolocation_override(latitude: Optional[float] = None, longitude: Optional[float] = None, accuracy: Optional[float] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    if latitude is not None:
        params['latitude'] = latitude
    if longitude is not None:
        params['longitude'] = longitude
    if accuracy is not None:
        params['accuracy'] = accuracy
    cmd: T_JSON_DICT = {"method": "Page.setGeolocationOverride", "params": params}
    return cmd, None


def set_lifecycle_events_enabled(enabled: bool) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['enabled'] = enabled
    cmd: T_JSON_DICT = {"method": "Page.setLifecycleEventsEnabled", "params": params}
    return cmd, None


def set_touch_emulation_enabled(enabled: bool, configuration: Optional[str] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['enabled'] = enabled
    if configuration is not None:
        params['configuration'] = configuration
    cmd: T_JSON_DICT = {"method": "Page.setTouchEmulationEnabled", "params": params}
    return cmd, None


def start_screencast(format: Optional[str] = None, quality: Optional[int] = None, max_width: Optional[int] = None, max_height: Optional[int] = None, every_nth_frame: Optional[int] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    if format is not None:
        params['format'] = format
    if quality is not None:
        params['quality'] = quality
    if max_width is not None:
        params['maxWidth'] = max_width
    if max_height is not None:
        params['maxHeight'] = max_height
    if every_nth_frame is not None:
        params['everyNthFrame'] = every_nth_frame
    cmd: T_JSON_DICT = {"method": "Page.startScreencast", "params": params}
    return cmd, None


def stop_loading() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Page.stopLoading", "params": params}
    return cmd, None


def crash() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Page.crash", "params": params}
    return cmd, None


def close() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Page.close", "params": params}
    return cmd, None


def set_web_lifecycle_state(state: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['state'] = state
    cmd: T_JSON_DICT = {"method": "Page.setWebLifecycleState", "params": params}
    return cmd, None


def stop_screencast() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Page.stopScreencast", "params": params}
    return cmd, None


def produce_compilation_cache(scripts: list[CompilationCacheParams]) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['scripts'] = [i.to_json() for i in scripts]
    cmd: T_JSON_DICT = {"method": "Page.produceCompilationCache", "params": params}
    return cmd, None


def add_compilation_cache(url: str, data: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['url'] = url
    params['data'] = data
    cmd: T_JSON_DICT = {"method": "Page.addCompilationCache", "params": params}
    return cmd, None


def clear_compilation_cache() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Page.clearCompilationCache", "params": params}
    return cmd, None


def set_spc_transaction_mode(mode: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['mode'] = mode
    cmd: T_JSON_DICT = {"method": "Page.setSPCTransactionMode", "params": params}
    return cmd, None


def set_rph_registration_mode(mode: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['mode'] = mode
    cmd: T_JSON_DICT = {"method": "Page.setRPHRegistrationMode", "params": params}
    return cmd, None


def generate_test_report(message: str, group: Optional[str] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['message'] = message
    if group is not None:
        params['group'] = group
    cmd: T_JSON_DICT = {"method": "Page.generateTestReport", "params": params}
    return cmd, None


def wait_for_debugger() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Page.waitForDebugger", "params": params}
    return cmd, None


def set_intercept_file_chooser_dialog(enabled: bool, cancel: Optional[bool] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['enabled'] = enabled
    if cancel is not None:
        params['cancel'] = cancel
    cmd: T_JSON_DICT = {"method": "Page.setInterceptFileChooserDialog", "params": params}
    return cmd, None


def set_prerendering_allowed(is_allowed: bool) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['isAllowed'] = is_allowed
    cmd: T_JSON_DICT = {"method": "Page.setPrerenderingAllowed", "params": params}
    return cmd, None


@dataclass
class GetAnnotatedPageContentResult:
    content: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetAnnotatedPageContentResult:
        return cls(
            content=str(data['content']),
        )


def get_annotated_page_content(include_actionable_information: Optional[bool] = None) -> tuple[T_JSON_DICT, type[GetAnnotatedPageContentResult]]:
    params: T_JSON_DICT = {}
    if include_actionable_information is not None:
        params['includeActionableInformation'] = include_actionable_information
    cmd: T_JSON_DICT = {"method": "Page.getAnnotatedPageContent", "params": params}
    return cmd, GetAnnotatedPageContentResult


@dataclass
class DomContentEventFired:
    EVENT_NAME: str = field(init=False, repr=False, default="Page.domContentEventFired")
    timestamp: MonotonicTime

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DomContentEventFired:
        return cls(
            timestamp=MonotonicTime.from_json(data['timestamp']),
        )


@dataclass
class FileChooserOpened:
    EVENT_NAME: str = field(init=False, repr=False, default="Page.fileChooserOpened")
    frame_id: FrameId
    mode: str
    backend_node_id: Optional[BackendNodeId] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> FileChooserOpened:
        return cls(
            frame_id=FrameId.from_json(data['frameId']),
            mode=str(data['mode']),
            backend_node_id=BackendNodeId.from_json(data['backendNodeId']) if 'backendNodeId' in data else None,
        )


@dataclass
class FrameAttached:
    EVENT_NAME: str = field(init=False, repr=False, default="Page.frameAttached")
    frame_id: FrameId
    parent_frame_id: FrameId
    stack: Optional[StackTrace] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> FrameAttached:
        return cls(
            frame_id=FrameId.from_json(data['frameId']),
            parent_frame_id=FrameId.from_json(data['parentFrameId']),
            stack=StackTrace.from_json(data['stack']) if 'stack' in data else None,
        )


@dataclass
class FrameClearedScheduledNavigation:
    EVENT_NAME: str = field(init=False, repr=False, default="Page.frameClearedScheduledNavigation")
    frame_id: FrameId

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> FrameClearedScheduledNavigation:
        return cls(
            frame_id=FrameId.from_json(data['frameId']),
        )


@dataclass
class FrameDetached:
    EVENT_NAME: str = field(init=False, repr=False, default="Page.frameDetached")
    frame_id: FrameId
    reason: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> FrameDetached:
        return cls(
            frame_id=FrameId.from_json(data['frameId']),
            reason=str(data['reason']),
        )


@dataclass
class FrameSubtreeWillBeDetached:
    EVENT_NAME: str = field(init=False, repr=False, default="Page.frameSubtreeWillBeDetached")
    frame_id: FrameId

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> FrameSubtreeWillBeDetached:
        return cls(
            frame_id=FrameId.from_json(data['frameId']),
        )


@dataclass
class FrameNavigated:
    EVENT_NAME: str = field(init=False, repr=False, default="Page.frameNavigated")
    frame: Frame
    type: NavigationType

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> FrameNavigated:
        return cls(
            frame=Frame.from_json(data['frame']),
            type=NavigationType.from_json(data['type']),
        )


@dataclass
class DocumentOpened:
    EVENT_NAME: str = field(init=False, repr=False, default="Page.documentOpened")
    frame: Frame

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DocumentOpened:
        return cls(
            frame=Frame.from_json(data['frame']),
        )


@dataclass
class FrameResized:
    EVENT_NAME: str = field(init=False, repr=False, default="Page.frameResized")

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> FrameResized:
        return cls()


@dataclass
class FrameStartedNavigating:
    EVENT_NAME: str = field(init=False, repr=False, default="Page.frameStartedNavigating")
    frame_id: FrameId
    url: str
    loader_id: LoaderId
    navigation_type: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> FrameStartedNavigating:
        return cls(
            frame_id=FrameId.from_json(data['frameId']),
            url=str(data['url']),
            loader_id=LoaderId.from_json(data['loaderId']),
            navigation_type=str(data['navigationType']),
        )


@dataclass
class FrameRequestedNavigation:
    EVENT_NAME: str = field(init=False, repr=False, default="Page.frameRequestedNavigation")
    frame_id: FrameId
    reason: ClientNavigationReason
    url: str
    disposition: ClientNavigationDisposition

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> FrameRequestedNavigation:
        return cls(
            frame_id=FrameId.from_json(data['frameId']),
            reason=ClientNavigationReason.from_json(data['reason']),
            url=str(data['url']),
            disposition=ClientNavigationDisposition.from_json(data['disposition']),
        )


@dataclass
class FrameScheduledNavigation:
    EVENT_NAME: str = field(init=False, repr=False, default="Page.frameScheduledNavigation")
    frame_id: FrameId
    delay: float
    reason: ClientNavigationReason
    url: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> FrameScheduledNavigation:
        return cls(
            frame_id=FrameId.from_json(data['frameId']),
            delay=float(data['delay']),
            reason=ClientNavigationReason.from_json(data['reason']),
            url=str(data['url']),
        )


@dataclass
class FrameStartedLoading:
    EVENT_NAME: str = field(init=False, repr=False, default="Page.frameStartedLoading")
    frame_id: FrameId

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> FrameStartedLoading:
        return cls(
            frame_id=FrameId.from_json(data['frameId']),
        )


@dataclass
class FrameStoppedLoading:
    EVENT_NAME: str = field(init=False, repr=False, default="Page.frameStoppedLoading")
    frame_id: FrameId

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> FrameStoppedLoading:
        return cls(
            frame_id=FrameId.from_json(data['frameId']),
        )


@dataclass
class DownloadWillBegin:
    EVENT_NAME: str = field(init=False, repr=False, default="Page.downloadWillBegin")
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
    EVENT_NAME: str = field(init=False, repr=False, default="Page.downloadProgress")
    guid: str
    total_bytes: float
    received_bytes: float
    state: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DownloadProgress:
        return cls(
            guid=str(data['guid']),
            total_bytes=float(data['totalBytes']),
            received_bytes=float(data['receivedBytes']),
            state=str(data['state']),
        )


@dataclass
class InterstitialHidden:
    EVENT_NAME: str = field(init=False, repr=False, default="Page.interstitialHidden")

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> InterstitialHidden:
        return cls()


@dataclass
class InterstitialShown:
    EVENT_NAME: str = field(init=False, repr=False, default="Page.interstitialShown")

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> InterstitialShown:
        return cls()


@dataclass
class JavascriptDialogClosed:
    EVENT_NAME: str = field(init=False, repr=False, default="Page.javascriptDialogClosed")
    frame_id: FrameId
    result: bool
    user_input: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> JavascriptDialogClosed:
        return cls(
            frame_id=FrameId.from_json(data['frameId']),
            result=bool(data['result']),
            user_input=str(data['userInput']),
        )


@dataclass
class JavascriptDialogOpening:
    EVENT_NAME: str = field(init=False, repr=False, default="Page.javascriptDialogOpening")
    url: str
    frame_id: FrameId
    message: str
    type: DialogType
    has_browser_handler: bool
    default_prompt: Optional[str] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> JavascriptDialogOpening:
        return cls(
            url=str(data['url']),
            frame_id=FrameId.from_json(data['frameId']),
            message=str(data['message']),
            type=DialogType.from_json(data['type']),
            has_browser_handler=bool(data['hasBrowserHandler']),
            default_prompt=str(data['defaultPrompt']) if 'defaultPrompt' in data else None,
        )


@dataclass
class LifecycleEvent:
    EVENT_NAME: str = field(init=False, repr=False, default="Page.lifecycleEvent")
    frame_id: FrameId
    loader_id: LoaderId
    name: str
    timestamp: MonotonicTime

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> LifecycleEvent:
        return cls(
            frame_id=FrameId.from_json(data['frameId']),
            loader_id=LoaderId.from_json(data['loaderId']),
            name=str(data['name']),
            timestamp=MonotonicTime.from_json(data['timestamp']),
        )


@dataclass
class BackForwardCacheNotUsed:
    EVENT_NAME: str = field(init=False, repr=False, default="Page.backForwardCacheNotUsed")
    loader_id: LoaderId
    frame_id: FrameId
    not_restored_explanations: list[BackForwardCacheNotRestoredExplanation]
    not_restored_explanations_tree: Optional[BackForwardCacheNotRestoredExplanationTree] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> BackForwardCacheNotUsed:
        return cls(
            loader_id=LoaderId.from_json(data['loaderId']),
            frame_id=FrameId.from_json(data['frameId']),
            not_restored_explanations=[BackForwardCacheNotRestoredExplanation.from_json(i) for i in data['notRestoredExplanations']],
            not_restored_explanations_tree=BackForwardCacheNotRestoredExplanationTree.from_json(data['notRestoredExplanationsTree']) if 'notRestoredExplanationsTree' in data else None,
        )


@dataclass
class LoadEventFired:
    EVENT_NAME: str = field(init=False, repr=False, default="Page.loadEventFired")
    timestamp: MonotonicTime

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> LoadEventFired:
        return cls(
            timestamp=MonotonicTime.from_json(data['timestamp']),
        )


@dataclass
class NavigatedWithinDocument:
    EVENT_NAME: str = field(init=False, repr=False, default="Page.navigatedWithinDocument")
    frame_id: FrameId
    url: str
    navigation_type: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> NavigatedWithinDocument:
        return cls(
            frame_id=FrameId.from_json(data['frameId']),
            url=str(data['url']),
            navigation_type=str(data['navigationType']),
        )


@dataclass
class ScreencastFrame:
    EVENT_NAME: str = field(init=False, repr=False, default="Page.screencastFrame")
    data: str
    metadata: ScreencastFrameMetadata
    session_id: int

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ScreencastFrame:
        return cls(
            data=str(data['data']),
            metadata=ScreencastFrameMetadata.from_json(data['metadata']),
            session_id=int(data['sessionId']),
        )


@dataclass
class ScreencastVisibilityChanged:
    EVENT_NAME: str = field(init=False, repr=False, default="Page.screencastVisibilityChanged")
    visible: bool

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ScreencastVisibilityChanged:
        return cls(
            visible=bool(data['visible']),
        )


@dataclass
class WindowOpen:
    EVENT_NAME: str = field(init=False, repr=False, default="Page.windowOpen")
    url: str
    window_name: str
    window_features: list[str]
    user_gesture: bool

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> WindowOpen:
        return cls(
            url=str(data['url']),
            window_name=str(data['windowName']),
            window_features=[str(i) for i in data['windowFeatures']],
            user_gesture=bool(data['userGesture']),
        )


@dataclass
class CompilationCacheProduced:
    EVENT_NAME: str = field(init=False, repr=False, default="Page.compilationCacheProduced")
    url: str
    data: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CompilationCacheProduced:
        return cls(
            url=str(data['url']),
            data=str(data['data']),
        )

