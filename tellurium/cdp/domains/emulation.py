"""Auto-generated CDP bindings for the Emulation domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from tellurium.cdp.types import T_JSON_DICT


@dataclass
class SafeAreaInsets:
    top: Optional[int] = None
    top_max: Optional[int] = None
    left: Optional[int] = None
    left_max: Optional[int] = None
    bottom: Optional[int] = None
    bottom_max: Optional[int] = None
    right: Optional[int] = None
    right_max: Optional[int] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        if self.top is not None:
            d['top'] = self.top
        if self.top_max is not None:
            d['topMax'] = self.top_max
        if self.left is not None:
            d['left'] = self.left
        if self.left_max is not None:
            d['leftMax'] = self.left_max
        if self.bottom is not None:
            d['bottom'] = self.bottom
        if self.bottom_max is not None:
            d['bottomMax'] = self.bottom_max
        if self.right is not None:
            d['right'] = self.right
        if self.right_max is not None:
            d['rightMax'] = self.right_max
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SafeAreaInsets:
        return cls(
            top=int(data['top']) if 'top' in data else None,
            top_max=int(data['topMax']) if 'topMax' in data else None,
            left=int(data['left']) if 'left' in data else None,
            left_max=int(data['leftMax']) if 'leftMax' in data else None,
            bottom=int(data['bottom']) if 'bottom' in data else None,
            bottom_max=int(data['bottomMax']) if 'bottomMax' in data else None,
            right=int(data['right']) if 'right' in data else None,
            right_max=int(data['rightMax']) if 'rightMax' in data else None,
        )


@dataclass
class ScreenOrientation:
    type: str
    angle: int

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['type'] = type
        d['angle'] = angle
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ScreenOrientation:
        return cls(
            type=str(data['type']),
            angle=int(data['angle']),
        )


@dataclass
class DisplayFeature:
    orientation: str
    offset: int
    mask_length: int

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['orientation'] = orientation
        d['offset'] = offset
        d['maskLength'] = mask_length
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DisplayFeature:
        return cls(
            orientation=str(data['orientation']),
            offset=int(data['offset']),
            mask_length=int(data['maskLength']),
        )


@dataclass
class DevicePosture:
    type: str

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['type'] = type
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DevicePosture:
        return cls(
            type=str(data['type']),
        )


@dataclass
class MediaFeature:
    name: str
    value: str

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['name'] = name
        d['value'] = value
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> MediaFeature:
        return cls(
            name=str(data['name']),
            value=str(data['value']),
        )


class VirtualTimePolicy(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> VirtualTimePolicy:
        return cls(val)


@dataclass
class UserAgentBrandVersion:
    brand: str
    version: str

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['brand'] = brand
        d['version'] = version
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> UserAgentBrandVersion:
        return cls(
            brand=str(data['brand']),
            version=str(data['version']),
        )


@dataclass
class UserAgentMetadata:
    platform: str
    platform_version: str
    architecture: str
    model: str
    mobile: bool
    brands: Optional[list[UserAgentBrandVersion]] = None
    full_version_list: Optional[list[UserAgentBrandVersion]] = None
    full_version: Optional[str] = None
    bitness: Optional[str] = None
    wow64: Optional[bool] = None
    form_factors: Optional[list[str]] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['platform'] = platform
        d['platformVersion'] = platform_version
        d['architecture'] = architecture
        d['model'] = model
        d['mobile'] = mobile
        if self.brands is not None:
            d['brands'] = [i.to_json() for i in self.brands]
        if self.full_version_list is not None:
            d['fullVersionList'] = [i.to_json() for i in self.full_version_list]
        if self.full_version is not None:
            d['fullVersion'] = self.full_version
        if self.bitness is not None:
            d['bitness'] = self.bitness
        if self.wow64 is not None:
            d['wow64'] = self.wow64
        if self.form_factors is not None:
            d['formFactors'] = list(self.form_factors)
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> UserAgentMetadata:
        return cls(
            platform=str(data['platform']),
            platform_version=str(data['platformVersion']),
            architecture=str(data['architecture']),
            model=str(data['model']),
            mobile=bool(data['mobile']),
            brands=[UserAgentBrandVersion.from_json(i) for i in data['brands']] if 'brands' in data else None,
            full_version_list=[UserAgentBrandVersion.from_json(i) for i in data['fullVersionList']] if 'fullVersionList' in data else None,
            full_version=str(data['fullVersion']) if 'fullVersion' in data else None,
            bitness=str(data['bitness']) if 'bitness' in data else None,
            wow64=bool(data['wow64']) if 'wow64' in data else None,
            form_factors=[str(i) for i in data['formFactors']] if 'formFactors' in data else None,
        )


class SensorType(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> SensorType:
        return cls(val)


@dataclass
class SensorMetadata:
    available: Optional[bool] = None
    minimum_frequency: Optional[float] = None
    maximum_frequency: Optional[float] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        if self.available is not None:
            d['available'] = self.available
        if self.minimum_frequency is not None:
            d['minimumFrequency'] = self.minimum_frequency
        if self.maximum_frequency is not None:
            d['maximumFrequency'] = self.maximum_frequency
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SensorMetadata:
        return cls(
            available=bool(data['available']) if 'available' in data else None,
            minimum_frequency=float(data['minimumFrequency']) if 'minimumFrequency' in data else None,
            maximum_frequency=float(data['maximumFrequency']) if 'maximumFrequency' in data else None,
        )


@dataclass
class SensorReadingSingle:
    value: float

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['value'] = value
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SensorReadingSingle:
        return cls(
            value=float(data['value']),
        )


@dataclass
class SensorReadingXYZ:
    x: float
    y: float
    z: float

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['x'] = x
        d['y'] = y
        d['z'] = z
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SensorReadingXYZ:
        return cls(
            x=float(data['x']),
            y=float(data['y']),
            z=float(data['z']),
        )


@dataclass
class SensorReadingQuaternion:
    x: float
    y: float
    z: float
    w: float

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['x'] = x
        d['y'] = y
        d['z'] = z
        d['w'] = w
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SensorReadingQuaternion:
        return cls(
            x=float(data['x']),
            y=float(data['y']),
            z=float(data['z']),
            w=float(data['w']),
        )


@dataclass
class SensorReading:
    single: Optional[SensorReadingSingle] = None
    xyz: Optional[SensorReadingXYZ] = None
    quaternion: Optional[SensorReadingQuaternion] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        if self.single is not None:
            d['single'] = self.single.to_json()
        if self.xyz is not None:
            d['xyz'] = self.xyz.to_json()
        if self.quaternion is not None:
            d['quaternion'] = self.quaternion.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SensorReading:
        return cls(
            single=SensorReadingSingle.from_json(data['single']) if 'single' in data else None,
            xyz=SensorReadingXYZ.from_json(data['xyz']) if 'xyz' in data else None,
            quaternion=SensorReadingQuaternion.from_json(data['quaternion']) if 'quaternion' in data else None,
        )


class PressureSource(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> PressureSource:
        return cls(val)


class PressureState(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> PressureState:
        return cls(val)


@dataclass
class PressureMetadata:
    available: Optional[bool] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        if self.available is not None:
            d['available'] = self.available
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> PressureMetadata:
        return cls(
            available=bool(data['available']) if 'available' in data else None,
        )


@dataclass
class WorkAreaInsets:
    top: Optional[int] = None
    left: Optional[int] = None
    bottom: Optional[int] = None
    right: Optional[int] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        if self.top is not None:
            d['top'] = self.top
        if self.left is not None:
            d['left'] = self.left
        if self.bottom is not None:
            d['bottom'] = self.bottom
        if self.right is not None:
            d['right'] = self.right
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> WorkAreaInsets:
        return cls(
            top=int(data['top']) if 'top' in data else None,
            left=int(data['left']) if 'left' in data else None,
            bottom=int(data['bottom']) if 'bottom' in data else None,
            right=int(data['right']) if 'right' in data else None,
        )


class ScreenId(str):
    """CDP string type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> ScreenId:
        return cls(val)


@dataclass
class ScreenInfo:
    left: int
    top: int
    width: int
    height: int
    avail_left: int
    avail_top: int
    avail_width: int
    avail_height: int
    device_pixel_ratio: float
    orientation: ScreenOrientation
    color_depth: int
    is_extended: bool
    is_internal: bool
    is_primary: bool
    label: str
    id: ScreenId

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['left'] = left
        d['top'] = top
        d['width'] = width
        d['height'] = height
        d['availLeft'] = avail_left
        d['availTop'] = avail_top
        d['availWidth'] = avail_width
        d['availHeight'] = avail_height
        d['devicePixelRatio'] = device_pixel_ratio
        d['orientation'] = orientation.to_json()
        d['colorDepth'] = color_depth
        d['isExtended'] = is_extended
        d['isInternal'] = is_internal
        d['isPrimary'] = is_primary
        d['label'] = label
        d['id'] = id.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ScreenInfo:
        return cls(
            left=int(data['left']),
            top=int(data['top']),
            width=int(data['width']),
            height=int(data['height']),
            avail_left=int(data['availLeft']),
            avail_top=int(data['availTop']),
            avail_width=int(data['availWidth']),
            avail_height=int(data['availHeight']),
            device_pixel_ratio=float(data['devicePixelRatio']),
            orientation=ScreenOrientation.from_json(data['orientation']),
            color_depth=int(data['colorDepth']),
            is_extended=bool(data['isExtended']),
            is_internal=bool(data['isInternal']),
            is_primary=bool(data['isPrimary']),
            label=str(data['label']),
            id=ScreenId.from_json(data['id']),
        )


class DisabledImageType(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> DisabledImageType:
        return cls(val)


@dataclass
class CanEmulateResult:
    result: bool

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CanEmulateResult:
        return cls(
            result=bool(data['result']),
        )


def can_emulate() -> tuple[T_JSON_DICT, type[CanEmulateResult]]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Emulation.canEmulate", "params": params}
    return cmd, CanEmulateResult


def clear_device_metrics_override() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Emulation.clearDeviceMetricsOverride", "params": params}
    return cmd, None


def clear_geolocation_override() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Emulation.clearGeolocationOverride", "params": params}
    return cmd, None


def reset_page_scale_factor() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Emulation.resetPageScaleFactor", "params": params}
    return cmd, None


def set_focus_emulation_enabled(enabled: bool) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['enabled'] = enabled
    cmd: T_JSON_DICT = {"method": "Emulation.setFocusEmulationEnabled", "params": params}
    return cmd, None


def set_auto_dark_mode_override(enabled: Optional[bool] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    if enabled is not None:
        params['enabled'] = enabled
    cmd: T_JSON_DICT = {"method": "Emulation.setAutoDarkModeOverride", "params": params}
    return cmd, None


def set_cpu_throttling_rate(rate: float) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['rate'] = rate
    cmd: T_JSON_DICT = {"method": "Emulation.setCPUThrottlingRate", "params": params}
    return cmd, None


def set_default_background_color_override(color: Optional[RGBA] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    if color is not None:
        params['color'] = color.to_json()
    cmd: T_JSON_DICT = {"method": "Emulation.setDefaultBackgroundColorOverride", "params": params}
    return cmd, None


def set_safe_area_insets_override(insets: SafeAreaInsets) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['insets'] = insets.to_json()
    cmd: T_JSON_DICT = {"method": "Emulation.setSafeAreaInsetsOverride", "params": params}
    return cmd, None


def set_device_metrics_override(width: int, height: int, device_scale_factor: float, mobile: bool, scale: Optional[float] = None, screen_width: Optional[int] = None, screen_height: Optional[int] = None, position_x: Optional[int] = None, position_y: Optional[int] = None, dont_set_visible_size: Optional[bool] = None, screen_orientation: Optional[ScreenOrientation] = None, viewport: Optional[Viewport] = None, display_feature: Optional[DisplayFeature] = None, device_posture: Optional[DevicePosture] = None, scrollbar_type: Optional[str] = None, screen_orientation_lock_emulation: Optional[bool] = None) -> tuple[T_JSON_DICT, None]:
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
    if display_feature is not None:
        params['displayFeature'] = display_feature.to_json()
    if device_posture is not None:
        params['devicePosture'] = device_posture.to_json()
    if scrollbar_type is not None:
        params['scrollbarType'] = scrollbar_type
    if screen_orientation_lock_emulation is not None:
        params['screenOrientationLockEmulation'] = screen_orientation_lock_emulation
    cmd: T_JSON_DICT = {"method": "Emulation.setDeviceMetricsOverride", "params": params}
    return cmd, None


def set_device_posture_override(posture: DevicePosture) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['posture'] = posture.to_json()
    cmd: T_JSON_DICT = {"method": "Emulation.setDevicePostureOverride", "params": params}
    return cmd, None


def clear_device_posture_override() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Emulation.clearDevicePostureOverride", "params": params}
    return cmd, None


def set_display_features_override(features: list[DisplayFeature]) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['features'] = [i.to_json() for i in features]
    cmd: T_JSON_DICT = {"method": "Emulation.setDisplayFeaturesOverride", "params": params}
    return cmd, None


def clear_display_features_override() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Emulation.clearDisplayFeaturesOverride", "params": params}
    return cmd, None


def set_scrollbars_hidden(hidden: bool) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['hidden'] = hidden
    cmd: T_JSON_DICT = {"method": "Emulation.setScrollbarsHidden", "params": params}
    return cmd, None


def set_document_cookie_disabled(disabled: bool) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['disabled'] = disabled
    cmd: T_JSON_DICT = {"method": "Emulation.setDocumentCookieDisabled", "params": params}
    return cmd, None


def set_emit_touch_events_for_mouse(enabled: bool, configuration: Optional[str] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['enabled'] = enabled
    if configuration is not None:
        params['configuration'] = configuration
    cmd: T_JSON_DICT = {"method": "Emulation.setEmitTouchEventsForMouse", "params": params}
    return cmd, None


def set_emulated_media(media: Optional[str] = None, features: Optional[list[MediaFeature]] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    if media is not None:
        params['media'] = media
    if features is not None:
        params['features'] = [i.to_json() for i in features]
    cmd: T_JSON_DICT = {"method": "Emulation.setEmulatedMedia", "params": params}
    return cmd, None


def set_emulated_vision_deficiency(type: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['type'] = type
    cmd: T_JSON_DICT = {"method": "Emulation.setEmulatedVisionDeficiency", "params": params}
    return cmd, None


def set_emulated_os_text_scale(scale: Optional[float] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    if scale is not None:
        params['scale'] = scale
    cmd: T_JSON_DICT = {"method": "Emulation.setEmulatedOSTextScale", "params": params}
    return cmd, None


def set_geolocation_override(latitude: Optional[float] = None, longitude: Optional[float] = None, accuracy: Optional[float] = None, altitude: Optional[float] = None, altitude_accuracy: Optional[float] = None, heading: Optional[float] = None, speed: Optional[float] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    if latitude is not None:
        params['latitude'] = latitude
    if longitude is not None:
        params['longitude'] = longitude
    if accuracy is not None:
        params['accuracy'] = accuracy
    if altitude is not None:
        params['altitude'] = altitude
    if altitude_accuracy is not None:
        params['altitudeAccuracy'] = altitude_accuracy
    if heading is not None:
        params['heading'] = heading
    if speed is not None:
        params['speed'] = speed
    cmd: T_JSON_DICT = {"method": "Emulation.setGeolocationOverride", "params": params}
    return cmd, None


@dataclass
class GetOverriddenSensorInformationResult:
    requested_sampling_frequency: float

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetOverriddenSensorInformationResult:
        return cls(
            requested_sampling_frequency=float(data['requestedSamplingFrequency']),
        )


def get_overridden_sensor_information(type: SensorType) -> tuple[T_JSON_DICT, type[GetOverriddenSensorInformationResult]]:
    params: T_JSON_DICT = {}
    params['type'] = type.to_json()
    cmd: T_JSON_DICT = {"method": "Emulation.getOverriddenSensorInformation", "params": params}
    return cmd, GetOverriddenSensorInformationResult


def set_sensor_override_enabled(enabled: bool, type: SensorType, metadata: Optional[SensorMetadata] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['enabled'] = enabled
    params['type'] = type.to_json()
    if metadata is not None:
        params['metadata'] = metadata.to_json()
    cmd: T_JSON_DICT = {"method": "Emulation.setSensorOverrideEnabled", "params": params}
    return cmd, None


def set_sensor_override_readings(type: SensorType, reading: SensorReading) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['type'] = type.to_json()
    params['reading'] = reading.to_json()
    cmd: T_JSON_DICT = {"method": "Emulation.setSensorOverrideReadings", "params": params}
    return cmd, None


def set_pressure_source_override_enabled(enabled: bool, source: PressureSource, metadata: Optional[PressureMetadata] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['enabled'] = enabled
    params['source'] = source.to_json()
    if metadata is not None:
        params['metadata'] = metadata.to_json()
    cmd: T_JSON_DICT = {"method": "Emulation.setPressureSourceOverrideEnabled", "params": params}
    return cmd, None


def set_pressure_state_override(source: PressureSource, state: PressureState) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['source'] = source.to_json()
    params['state'] = state.to_json()
    cmd: T_JSON_DICT = {"method": "Emulation.setPressureStateOverride", "params": params}
    return cmd, None


def set_pressure_data_override(source: PressureSource, state: PressureState, own_contribution_estimate: Optional[float] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['source'] = source.to_json()
    params['state'] = state.to_json()
    if own_contribution_estimate is not None:
        params['ownContributionEstimate'] = own_contribution_estimate
    cmd: T_JSON_DICT = {"method": "Emulation.setPressureDataOverride", "params": params}
    return cmd, None


def set_idle_override(is_user_active: bool, is_screen_unlocked: bool) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['isUserActive'] = is_user_active
    params['isScreenUnlocked'] = is_screen_unlocked
    cmd: T_JSON_DICT = {"method": "Emulation.setIdleOverride", "params": params}
    return cmd, None


def clear_idle_override() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Emulation.clearIdleOverride", "params": params}
    return cmd, None


def set_navigator_overrides(platform: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['platform'] = platform
    cmd: T_JSON_DICT = {"method": "Emulation.setNavigatorOverrides", "params": params}
    return cmd, None


def set_page_scale_factor(page_scale_factor: float) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['pageScaleFactor'] = page_scale_factor
    cmd: T_JSON_DICT = {"method": "Emulation.setPageScaleFactor", "params": params}
    return cmd, None


def set_script_execution_disabled(value: bool) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['value'] = value
    cmd: T_JSON_DICT = {"method": "Emulation.setScriptExecutionDisabled", "params": params}
    return cmd, None


def set_touch_emulation_enabled(enabled: bool, max_touch_points: Optional[int] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['enabled'] = enabled
    if max_touch_points is not None:
        params['maxTouchPoints'] = max_touch_points
    cmd: T_JSON_DICT = {"method": "Emulation.setTouchEmulationEnabled", "params": params}
    return cmd, None


@dataclass
class SetVirtualTimePolicyResult:
    virtual_time_ticks_base: float

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SetVirtualTimePolicyResult:
        return cls(
            virtual_time_ticks_base=float(data['virtualTimeTicksBase']),
        )


def set_virtual_time_policy(policy: VirtualTimePolicy, budget: Optional[float] = None, max_virtual_time_task_starvation_count: Optional[int] = None, initial_virtual_time: Optional[TimeSinceEpoch] = None) -> tuple[T_JSON_DICT, type[SetVirtualTimePolicyResult]]:
    params: T_JSON_DICT = {}
    params['policy'] = policy.to_json()
    if budget is not None:
        params['budget'] = budget
    if max_virtual_time_task_starvation_count is not None:
        params['maxVirtualTimeTaskStarvationCount'] = max_virtual_time_task_starvation_count
    if initial_virtual_time is not None:
        params['initialVirtualTime'] = initial_virtual_time.to_json()
    cmd: T_JSON_DICT = {"method": "Emulation.setVirtualTimePolicy", "params": params}
    return cmd, SetVirtualTimePolicyResult


def set_locale_override(locale: Optional[str] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    if locale is not None:
        params['locale'] = locale
    cmd: T_JSON_DICT = {"method": "Emulation.setLocaleOverride", "params": params}
    return cmd, None


def set_timezone_override(timezone_id: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['timezoneId'] = timezone_id
    cmd: T_JSON_DICT = {"method": "Emulation.setTimezoneOverride", "params": params}
    return cmd, None


def set_visible_size(width: int, height: int) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['width'] = width
    params['height'] = height
    cmd: T_JSON_DICT = {"method": "Emulation.setVisibleSize", "params": params}
    return cmd, None


def set_disabled_image_types(image_types: list[DisabledImageType]) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['imageTypes'] = [i.to_json() for i in image_types]
    cmd: T_JSON_DICT = {"method": "Emulation.setDisabledImageTypes", "params": params}
    return cmd, None


def set_data_saver_override(data_saver_enabled: Optional[bool] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    if data_saver_enabled is not None:
        params['dataSaverEnabled'] = data_saver_enabled
    cmd: T_JSON_DICT = {"method": "Emulation.setDataSaverOverride", "params": params}
    return cmd, None


def set_hardware_concurrency_override(hardware_concurrency: int) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['hardwareConcurrency'] = hardware_concurrency
    cmd: T_JSON_DICT = {"method": "Emulation.setHardwareConcurrencyOverride", "params": params}
    return cmd, None


def set_user_agent_override(user_agent: str, accept_language: Optional[str] = None, platform: Optional[str] = None, user_agent_metadata: Optional[UserAgentMetadata] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['userAgent'] = user_agent
    if accept_language is not None:
        params['acceptLanguage'] = accept_language
    if platform is not None:
        params['platform'] = platform
    if user_agent_metadata is not None:
        params['userAgentMetadata'] = user_agent_metadata.to_json()
    cmd: T_JSON_DICT = {"method": "Emulation.setUserAgentOverride", "params": params}
    return cmd, None


def set_automation_override(enabled: bool) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['enabled'] = enabled
    cmd: T_JSON_DICT = {"method": "Emulation.setAutomationOverride", "params": params}
    return cmd, None


def set_small_viewport_height_difference_override(difference: int) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['difference'] = difference
    cmd: T_JSON_DICT = {"method": "Emulation.setSmallViewportHeightDifferenceOverride", "params": params}
    return cmd, None


@dataclass
class GetScreenInfosResult:
    screen_infos: list[ScreenInfo]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetScreenInfosResult:
        return cls(
            screen_infos=[ScreenInfo.from_json(i) for i in data['screenInfos']],
        )


def get_screen_infos() -> tuple[T_JSON_DICT, type[GetScreenInfosResult]]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Emulation.getScreenInfos", "params": params}
    return cmd, GetScreenInfosResult


@dataclass
class AddScreenResult:
    screen_info: ScreenInfo

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> AddScreenResult:
        return cls(
            screen_info=ScreenInfo.from_json(data['screenInfo']),
        )


def add_screen(left: int, top: int, width: int, height: int, work_area_insets: Optional[WorkAreaInsets] = None, device_pixel_ratio: Optional[float] = None, rotation: Optional[int] = None, color_depth: Optional[int] = None, label: Optional[str] = None, is_internal: Optional[bool] = None) -> tuple[T_JSON_DICT, type[AddScreenResult]]:
    params: T_JSON_DICT = {}
    params['left'] = left
    params['top'] = top
    params['width'] = width
    params['height'] = height
    if work_area_insets is not None:
        params['workAreaInsets'] = work_area_insets.to_json()
    if device_pixel_ratio is not None:
        params['devicePixelRatio'] = device_pixel_ratio
    if rotation is not None:
        params['rotation'] = rotation
    if color_depth is not None:
        params['colorDepth'] = color_depth
    if label is not None:
        params['label'] = label
    if is_internal is not None:
        params['isInternal'] = is_internal
    cmd: T_JSON_DICT = {"method": "Emulation.addScreen", "params": params}
    return cmd, AddScreenResult


@dataclass
class UpdateScreenResult:
    screen_info: ScreenInfo

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> UpdateScreenResult:
        return cls(
            screen_info=ScreenInfo.from_json(data['screenInfo']),
        )


def update_screen(screen_id: ScreenId, left: Optional[int] = None, top: Optional[int] = None, width: Optional[int] = None, height: Optional[int] = None, work_area_insets: Optional[WorkAreaInsets] = None, device_pixel_ratio: Optional[float] = None, rotation: Optional[int] = None, color_depth: Optional[int] = None, label: Optional[str] = None, is_internal: Optional[bool] = None) -> tuple[T_JSON_DICT, type[UpdateScreenResult]]:
    params: T_JSON_DICT = {}
    params['screenId'] = screen_id.to_json()
    if left is not None:
        params['left'] = left
    if top is not None:
        params['top'] = top
    if width is not None:
        params['width'] = width
    if height is not None:
        params['height'] = height
    if work_area_insets is not None:
        params['workAreaInsets'] = work_area_insets.to_json()
    if device_pixel_ratio is not None:
        params['devicePixelRatio'] = device_pixel_ratio
    if rotation is not None:
        params['rotation'] = rotation
    if color_depth is not None:
        params['colorDepth'] = color_depth
    if label is not None:
        params['label'] = label
    if is_internal is not None:
        params['isInternal'] = is_internal
    cmd: T_JSON_DICT = {"method": "Emulation.updateScreen", "params": params}
    return cmd, UpdateScreenResult


def remove_screen(screen_id: ScreenId) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['screenId'] = screen_id.to_json()
    cmd: T_JSON_DICT = {"method": "Emulation.removeScreen", "params": params}
    return cmd, None


def set_primary_screen(screen_id: ScreenId) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['screenId'] = screen_id.to_json()
    cmd: T_JSON_DICT = {"method": "Emulation.setPrimaryScreen", "params": params}
    return cmd, None


@dataclass
class VirtualTimeBudgetExpired:
    EVENT_NAME: str = field(init=False, repr=False, default="Emulation.virtualTimeBudgetExpired")

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> VirtualTimeBudgetExpired:
        return cls()


@dataclass
class ScreenOrientationLockChanged:
    EVENT_NAME: str = field(init=False, repr=False, default="Emulation.screenOrientationLockChanged")
    locked: bool
    orientation: Optional[ScreenOrientation] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ScreenOrientationLockChanged:
        return cls(
            locked=bool(data['locked']),
            orientation=ScreenOrientation.from_json(data['orientation']) if 'orientation' in data else None,
        )

