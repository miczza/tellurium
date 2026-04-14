"""Auto-generated CDP bindings for the Input domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from tellurium.cdp.types import T_JSON_DICT


@dataclass
class TouchPoint:
    x: float
    y: float
    radius_x: Optional[float] = None
    radius_y: Optional[float] = None
    rotation_angle: Optional[float] = None
    force: Optional[float] = None
    tangential_pressure: Optional[float] = None
    tilt_x: Optional[float] = None
    tilt_y: Optional[float] = None
    twist: Optional[int] = None
    id: Optional[float] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['x'] = x
        d['y'] = y
        if self.radius_x is not None:
            d['radiusX'] = self.radius_x
        if self.radius_y is not None:
            d['radiusY'] = self.radius_y
        if self.rotation_angle is not None:
            d['rotationAngle'] = self.rotation_angle
        if self.force is not None:
            d['force'] = self.force
        if self.tangential_pressure is not None:
            d['tangentialPressure'] = self.tangential_pressure
        if self.tilt_x is not None:
            d['tiltX'] = self.tilt_x
        if self.tilt_y is not None:
            d['tiltY'] = self.tilt_y
        if self.twist is not None:
            d['twist'] = self.twist
        if self.id is not None:
            d['id'] = self.id
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> TouchPoint:
        return cls(
            x=float(data['x']),
            y=float(data['y']),
            radius_x=float(data['radiusX']) if 'radiusX' in data else None,
            radius_y=float(data['radiusY']) if 'radiusY' in data else None,
            rotation_angle=float(data['rotationAngle']) if 'rotationAngle' in data else None,
            force=float(data['force']) if 'force' in data else None,
            tangential_pressure=float(data['tangentialPressure']) if 'tangentialPressure' in data else None,
            tilt_x=float(data['tiltX']) if 'tiltX' in data else None,
            tilt_y=float(data['tiltY']) if 'tiltY' in data else None,
            twist=int(data['twist']) if 'twist' in data else None,
            id=float(data['id']) if 'id' in data else None,
        )


class GestureSourceType(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> GestureSourceType:
        return cls(val)


class MouseButton(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> MouseButton:
        return cls(val)


class TimeSinceEpoch(float):
    """CDP type alias."""

    def to_json(self) -> float:
        return float(self)

    @classmethod
    def from_json(cls, val: float) -> TimeSinceEpoch:
        return cls(val)


@dataclass
class DragDataItem:
    mime_type: str
    data: str
    title: Optional[str] = None
    base_url: Optional[str] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['mimeType'] = mime_type
        d['data'] = data
        if self.title is not None:
            d['title'] = self.title
        if self.base_url is not None:
            d['baseURL'] = self.base_url
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DragDataItem:
        return cls(
            mime_type=str(data['mimeType']),
            data=str(data['data']),
            title=str(data['title']) if 'title' in data else None,
            base_url=str(data['baseURL']) if 'baseURL' in data else None,
        )


@dataclass
class DragData:
    items: list[DragDataItem]
    drag_operations_mask: int
    files: Optional[list[str]] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['items'] = [i.to_json() for i in items]
        d['dragOperationsMask'] = drag_operations_mask
        if self.files is not None:
            d['files'] = list(self.files)
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DragData:
        return cls(
            items=[DragDataItem.from_json(i) for i in data['items']],
            drag_operations_mask=int(data['dragOperationsMask']),
            files=[str(i) for i in data['files']] if 'files' in data else None,
        )


def dispatch_drag_event(type: str, x: float, y: float, data: DragData, modifiers: Optional[int] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['type'] = type
    params['x'] = x
    params['y'] = y
    params['data'] = data.to_json()
    if modifiers is not None:
        params['modifiers'] = modifiers
    cmd: T_JSON_DICT = {"method": "Input.dispatchDragEvent", "params": params}
    return cmd, None


def dispatch_key_event(type: str, modifiers: Optional[int] = None, timestamp: Optional[TimeSinceEpoch] = None, text: Optional[str] = None, unmodified_text: Optional[str] = None, key_identifier: Optional[str] = None, code: Optional[str] = None, key: Optional[str] = None, windows_virtual_key_code: Optional[int] = None, native_virtual_key_code: Optional[int] = None, auto_repeat: Optional[bool] = None, is_keypad: Optional[bool] = None, is_system_key: Optional[bool] = None, location: Optional[int] = None, commands: Optional[list[str]] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['type'] = type
    if modifiers is not None:
        params['modifiers'] = modifiers
    if timestamp is not None:
        params['timestamp'] = timestamp.to_json()
    if text is not None:
        params['text'] = text
    if unmodified_text is not None:
        params['unmodifiedText'] = unmodified_text
    if key_identifier is not None:
        params['keyIdentifier'] = key_identifier
    if code is not None:
        params['code'] = code
    if key is not None:
        params['key'] = key
    if windows_virtual_key_code is not None:
        params['windowsVirtualKeyCode'] = windows_virtual_key_code
    if native_virtual_key_code is not None:
        params['nativeVirtualKeyCode'] = native_virtual_key_code
    if auto_repeat is not None:
        params['autoRepeat'] = auto_repeat
    if is_keypad is not None:
        params['isKeypad'] = is_keypad
    if is_system_key is not None:
        params['isSystemKey'] = is_system_key
    if location is not None:
        params['location'] = location
    if commands is not None:
        params['commands'] = list(commands)
    cmd: T_JSON_DICT = {"method": "Input.dispatchKeyEvent", "params": params}
    return cmd, None


def insert_text(text: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['text'] = text
    cmd: T_JSON_DICT = {"method": "Input.insertText", "params": params}
    return cmd, None


def ime_set_composition(text: str, selection_start: int, selection_end: int, replacement_start: Optional[int] = None, replacement_end: Optional[int] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['text'] = text
    params['selectionStart'] = selection_start
    params['selectionEnd'] = selection_end
    if replacement_start is not None:
        params['replacementStart'] = replacement_start
    if replacement_end is not None:
        params['replacementEnd'] = replacement_end
    cmd: T_JSON_DICT = {"method": "Input.imeSetComposition", "params": params}
    return cmd, None


def dispatch_mouse_event(type: str, x: float, y: float, modifiers: Optional[int] = None, timestamp: Optional[TimeSinceEpoch] = None, button: Optional[MouseButton] = None, buttons: Optional[int] = None, click_count: Optional[int] = None, force: Optional[float] = None, tangential_pressure: Optional[float] = None, tilt_x: Optional[float] = None, tilt_y: Optional[float] = None, twist: Optional[int] = None, delta_x: Optional[float] = None, delta_y: Optional[float] = None, pointer_type: Optional[str] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['type'] = type
    params['x'] = x
    params['y'] = y
    if modifiers is not None:
        params['modifiers'] = modifiers
    if timestamp is not None:
        params['timestamp'] = timestamp.to_json()
    if button is not None:
        params['button'] = button.to_json()
    if buttons is not None:
        params['buttons'] = buttons
    if click_count is not None:
        params['clickCount'] = click_count
    if force is not None:
        params['force'] = force
    if tangential_pressure is not None:
        params['tangentialPressure'] = tangential_pressure
    if tilt_x is not None:
        params['tiltX'] = tilt_x
    if tilt_y is not None:
        params['tiltY'] = tilt_y
    if twist is not None:
        params['twist'] = twist
    if delta_x is not None:
        params['deltaX'] = delta_x
    if delta_y is not None:
        params['deltaY'] = delta_y
    if pointer_type is not None:
        params['pointerType'] = pointer_type
    cmd: T_JSON_DICT = {"method": "Input.dispatchMouseEvent", "params": params}
    return cmd, None


def dispatch_touch_event(type: str, touch_points: list[TouchPoint], modifiers: Optional[int] = None, timestamp: Optional[TimeSinceEpoch] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['type'] = type
    params['touchPoints'] = [i.to_json() for i in touch_points]
    if modifiers is not None:
        params['modifiers'] = modifiers
    if timestamp is not None:
        params['timestamp'] = timestamp.to_json()
    cmd: T_JSON_DICT = {"method": "Input.dispatchTouchEvent", "params": params}
    return cmd, None


def cancel_dragging() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Input.cancelDragging", "params": params}
    return cmd, None


def emulate_touch_from_mouse_event(type: str, x: int, y: int, button: MouseButton, timestamp: Optional[TimeSinceEpoch] = None, delta_x: Optional[float] = None, delta_y: Optional[float] = None, modifiers: Optional[int] = None, click_count: Optional[int] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['type'] = type
    params['x'] = x
    params['y'] = y
    params['button'] = button.to_json()
    if timestamp is not None:
        params['timestamp'] = timestamp.to_json()
    if delta_x is not None:
        params['deltaX'] = delta_x
    if delta_y is not None:
        params['deltaY'] = delta_y
    if modifiers is not None:
        params['modifiers'] = modifiers
    if click_count is not None:
        params['clickCount'] = click_count
    cmd: T_JSON_DICT = {"method": "Input.emulateTouchFromMouseEvent", "params": params}
    return cmd, None


def set_ignore_input_events(ignore: bool) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['ignore'] = ignore
    cmd: T_JSON_DICT = {"method": "Input.setIgnoreInputEvents", "params": params}
    return cmd, None


def set_intercept_drags(enabled: bool) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['enabled'] = enabled
    cmd: T_JSON_DICT = {"method": "Input.setInterceptDrags", "params": params}
    return cmd, None


def synthesize_pinch_gesture(x: float, y: float, scale_factor: float, relative_speed: Optional[int] = None, gesture_source_type: Optional[GestureSourceType] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['x'] = x
    params['y'] = y
    params['scaleFactor'] = scale_factor
    if relative_speed is not None:
        params['relativeSpeed'] = relative_speed
    if gesture_source_type is not None:
        params['gestureSourceType'] = gesture_source_type.to_json()
    cmd: T_JSON_DICT = {"method": "Input.synthesizePinchGesture", "params": params}
    return cmd, None


def synthesize_scroll_gesture(x: float, y: float, x_distance: Optional[float] = None, y_distance: Optional[float] = None, x_overscroll: Optional[float] = None, y_overscroll: Optional[float] = None, prevent_fling: Optional[bool] = None, speed: Optional[int] = None, gesture_source_type: Optional[GestureSourceType] = None, repeat_count: Optional[int] = None, repeat_delay_ms: Optional[int] = None, interaction_marker_name: Optional[str] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['x'] = x
    params['y'] = y
    if x_distance is not None:
        params['xDistance'] = x_distance
    if y_distance is not None:
        params['yDistance'] = y_distance
    if x_overscroll is not None:
        params['xOverscroll'] = x_overscroll
    if y_overscroll is not None:
        params['yOverscroll'] = y_overscroll
    if prevent_fling is not None:
        params['preventFling'] = prevent_fling
    if speed is not None:
        params['speed'] = speed
    if gesture_source_type is not None:
        params['gestureSourceType'] = gesture_source_type.to_json()
    if repeat_count is not None:
        params['repeatCount'] = repeat_count
    if repeat_delay_ms is not None:
        params['repeatDelayMs'] = repeat_delay_ms
    if interaction_marker_name is not None:
        params['interactionMarkerName'] = interaction_marker_name
    cmd: T_JSON_DICT = {"method": "Input.synthesizeScrollGesture", "params": params}
    return cmd, None


def synthesize_tap_gesture(x: float, y: float, duration: Optional[int] = None, tap_count: Optional[int] = None, gesture_source_type: Optional[GestureSourceType] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['x'] = x
    params['y'] = y
    if duration is not None:
        params['duration'] = duration
    if tap_count is not None:
        params['tapCount'] = tap_count
    if gesture_source_type is not None:
        params['gestureSourceType'] = gesture_source_type.to_json()
    cmd: T_JSON_DICT = {"method": "Input.synthesizeTapGesture", "params": params}
    return cmd, None


@dataclass
class DragIntercepted:
    EVENT_NAME: str = field(init=False, repr=False, default="Input.dragIntercepted")
    data: DragData

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DragIntercepted:
        return cls(
            data=DragData.from_json(data['data']),
        )

