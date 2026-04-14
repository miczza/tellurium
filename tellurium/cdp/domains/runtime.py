"""Auto-generated CDP bindings for the Runtime domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from tellurium.cdp.types import T_JSON_DICT


class ScriptId(str):
    """CDP string type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> ScriptId:
        return cls(val)


@dataclass
class SerializationOptions:
    serialization: str
    max_depth: Optional[int] = None
    additional_parameters: Optional[T_JSON_DICT] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['serialization'] = serialization
        if self.max_depth is not None:
            d['maxDepth'] = self.max_depth
        if self.additional_parameters is not None:
            d['additionalParameters'] = self.additional_parameters
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SerializationOptions:
        return cls(
            serialization=str(data['serialization']),
            max_depth=int(data['maxDepth']) if 'maxDepth' in data else None,
            additional_parameters=data['additionalParameters'] if 'additionalParameters' in data else None,
        )


@dataclass
class DeepSerializedValue:
    type: str
    value: Optional[Any] = None
    object_id: Optional[str] = None
    weak_local_object_reference: Optional[int] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['type'] = type
        if self.value is not None:
            d['value'] = self.value
        if self.object_id is not None:
            d['objectId'] = self.object_id
        if self.weak_local_object_reference is not None:
            d['weakLocalObjectReference'] = self.weak_local_object_reference
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DeepSerializedValue:
        return cls(
            type=str(data['type']),
            value=data['value'] if 'value' in data else None,
            object_id=str(data['objectId']) if 'objectId' in data else None,
            weak_local_object_reference=int(data['weakLocalObjectReference']) if 'weakLocalObjectReference' in data else None,
        )


class RemoteObjectId(str):
    """CDP string type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> RemoteObjectId:
        return cls(val)


class UnserializableValue(str):
    """CDP string type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> UnserializableValue:
        return cls(val)


@dataclass
class RemoteObject:
    type: str
    subtype: Optional[str] = None
    class_name: Optional[str] = None
    value: Optional[Any] = None
    unserializable_value: Optional[UnserializableValue] = None
    description: Optional[str] = None
    deep_serialized_value: Optional[DeepSerializedValue] = None
    object_id: Optional[RemoteObjectId] = None
    preview: Optional[ObjectPreview] = None
    custom_preview: Optional[CustomPreview] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['type'] = type
        if self.subtype is not None:
            d['subtype'] = self.subtype
        if self.class_name is not None:
            d['className'] = self.class_name
        if self.value is not None:
            d['value'] = self.value
        if self.unserializable_value is not None:
            d['unserializableValue'] = self.unserializable_value.to_json()
        if self.description is not None:
            d['description'] = self.description
        if self.deep_serialized_value is not None:
            d['deepSerializedValue'] = self.deep_serialized_value.to_json()
        if self.object_id is not None:
            d['objectId'] = self.object_id.to_json()
        if self.preview is not None:
            d['preview'] = self.preview.to_json()
        if self.custom_preview is not None:
            d['customPreview'] = self.custom_preview.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> RemoteObject:
        return cls(
            type=str(data['type']),
            subtype=str(data['subtype']) if 'subtype' in data else None,
            class_name=str(data['className']) if 'className' in data else None,
            value=data['value'] if 'value' in data else None,
            unserializable_value=UnserializableValue.from_json(data['unserializableValue']) if 'unserializableValue' in data else None,
            description=str(data['description']) if 'description' in data else None,
            deep_serialized_value=DeepSerializedValue.from_json(data['deepSerializedValue']) if 'deepSerializedValue' in data else None,
            object_id=RemoteObjectId.from_json(data['objectId']) if 'objectId' in data else None,
            preview=ObjectPreview.from_json(data['preview']) if 'preview' in data else None,
            custom_preview=CustomPreview.from_json(data['customPreview']) if 'customPreview' in data else None,
        )


@dataclass
class CustomPreview:
    header: str
    body_getter_id: Optional[RemoteObjectId] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['header'] = header
        if self.body_getter_id is not None:
            d['bodyGetterId'] = self.body_getter_id.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CustomPreview:
        return cls(
            header=str(data['header']),
            body_getter_id=RemoteObjectId.from_json(data['bodyGetterId']) if 'bodyGetterId' in data else None,
        )


@dataclass
class ObjectPreview:
    type: str
    overflow: bool
    properties: list[PropertyPreview]
    subtype: Optional[str] = None
    description: Optional[str] = None
    entries: Optional[list[EntryPreview]] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['type'] = type
        d['overflow'] = overflow
        d['properties'] = [i.to_json() for i in properties]
        if self.subtype is not None:
            d['subtype'] = self.subtype
        if self.description is not None:
            d['description'] = self.description
        if self.entries is not None:
            d['entries'] = [i.to_json() for i in self.entries]
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ObjectPreview:
        return cls(
            type=str(data['type']),
            overflow=bool(data['overflow']),
            properties=[PropertyPreview.from_json(i) for i in data['properties']],
            subtype=str(data['subtype']) if 'subtype' in data else None,
            description=str(data['description']) if 'description' in data else None,
            entries=[EntryPreview.from_json(i) for i in data['entries']] if 'entries' in data else None,
        )


@dataclass
class PropertyPreview:
    name: str
    type: str
    value: Optional[str] = None
    value_preview: Optional[ObjectPreview] = None
    subtype: Optional[str] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['name'] = name
        d['type'] = type
        if self.value is not None:
            d['value'] = self.value
        if self.value_preview is not None:
            d['valuePreview'] = self.value_preview.to_json()
        if self.subtype is not None:
            d['subtype'] = self.subtype
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> PropertyPreview:
        return cls(
            name=str(data['name']),
            type=str(data['type']),
            value=str(data['value']) if 'value' in data else None,
            value_preview=ObjectPreview.from_json(data['valuePreview']) if 'valuePreview' in data else None,
            subtype=str(data['subtype']) if 'subtype' in data else None,
        )


@dataclass
class EntryPreview:
    value: ObjectPreview
    key: Optional[ObjectPreview] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['value'] = value.to_json()
        if self.key is not None:
            d['key'] = self.key.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> EntryPreview:
        return cls(
            value=ObjectPreview.from_json(data['value']),
            key=ObjectPreview.from_json(data['key']) if 'key' in data else None,
        )


@dataclass
class PropertyDescriptor:
    name: str
    configurable: bool
    enumerable: bool
    value: Optional[RemoteObject] = None
    writable: Optional[bool] = None
    get: Optional[RemoteObject] = None
    set: Optional[RemoteObject] = None
    was_thrown: Optional[bool] = None
    is_own: Optional[bool] = None
    symbol: Optional[RemoteObject] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['name'] = name
        d['configurable'] = configurable
        d['enumerable'] = enumerable
        if self.value is not None:
            d['value'] = self.value.to_json()
        if self.writable is not None:
            d['writable'] = self.writable
        if self.get is not None:
            d['get'] = self.get.to_json()
        if self.set is not None:
            d['set'] = self.set.to_json()
        if self.was_thrown is not None:
            d['wasThrown'] = self.was_thrown
        if self.is_own is not None:
            d['isOwn'] = self.is_own
        if self.symbol is not None:
            d['symbol'] = self.symbol.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> PropertyDescriptor:
        return cls(
            name=str(data['name']),
            configurable=bool(data['configurable']),
            enumerable=bool(data['enumerable']),
            value=RemoteObject.from_json(data['value']) if 'value' in data else None,
            writable=bool(data['writable']) if 'writable' in data else None,
            get=RemoteObject.from_json(data['get']) if 'get' in data else None,
            set=RemoteObject.from_json(data['set']) if 'set' in data else None,
            was_thrown=bool(data['wasThrown']) if 'wasThrown' in data else None,
            is_own=bool(data['isOwn']) if 'isOwn' in data else None,
            symbol=RemoteObject.from_json(data['symbol']) if 'symbol' in data else None,
        )


@dataclass
class InternalPropertyDescriptor:
    name: str
    value: Optional[RemoteObject] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['name'] = name
        if self.value is not None:
            d['value'] = self.value.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> InternalPropertyDescriptor:
        return cls(
            name=str(data['name']),
            value=RemoteObject.from_json(data['value']) if 'value' in data else None,
        )


@dataclass
class PrivatePropertyDescriptor:
    name: str
    value: Optional[RemoteObject] = None
    get: Optional[RemoteObject] = None
    set: Optional[RemoteObject] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['name'] = name
        if self.value is not None:
            d['value'] = self.value.to_json()
        if self.get is not None:
            d['get'] = self.get.to_json()
        if self.set is not None:
            d['set'] = self.set.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> PrivatePropertyDescriptor:
        return cls(
            name=str(data['name']),
            value=RemoteObject.from_json(data['value']) if 'value' in data else None,
            get=RemoteObject.from_json(data['get']) if 'get' in data else None,
            set=RemoteObject.from_json(data['set']) if 'set' in data else None,
        )


@dataclass
class CallArgument:
    value: Optional[Any] = None
    unserializable_value: Optional[UnserializableValue] = None
    object_id: Optional[RemoteObjectId] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        if self.value is not None:
            d['value'] = self.value
        if self.unserializable_value is not None:
            d['unserializableValue'] = self.unserializable_value.to_json()
        if self.object_id is not None:
            d['objectId'] = self.object_id.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CallArgument:
        return cls(
            value=data['value'] if 'value' in data else None,
            unserializable_value=UnserializableValue.from_json(data['unserializableValue']) if 'unserializableValue' in data else None,
            object_id=RemoteObjectId.from_json(data['objectId']) if 'objectId' in data else None,
        )


class ExecutionContextId(int):
    """CDP type alias."""

    def to_json(self) -> int:
        return int(self)

    @classmethod
    def from_json(cls, val: int) -> ExecutionContextId:
        return cls(val)


@dataclass
class ExecutionContextDescription:
    id: ExecutionContextId
    origin: str
    name: str
    unique_id: str
    aux_data: Optional[T_JSON_DICT] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['id'] = id.to_json()
        d['origin'] = origin
        d['name'] = name
        d['uniqueId'] = unique_id
        if self.aux_data is not None:
            d['auxData'] = self.aux_data
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ExecutionContextDescription:
        return cls(
            id=ExecutionContextId.from_json(data['id']),
            origin=str(data['origin']),
            name=str(data['name']),
            unique_id=str(data['uniqueId']),
            aux_data=data['auxData'] if 'auxData' in data else None,
        )


@dataclass
class ExceptionDetails:
    exception_id: int
    text: str
    line_number: int
    column_number: int
    script_id: Optional[ScriptId] = None
    url: Optional[str] = None
    stack_trace: Optional[StackTrace] = None
    exception: Optional[RemoteObject] = None
    execution_context_id: Optional[ExecutionContextId] = None
    exception_meta_data: Optional[T_JSON_DICT] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['exceptionId'] = exception_id
        d['text'] = text
        d['lineNumber'] = line_number
        d['columnNumber'] = column_number
        if self.script_id is not None:
            d['scriptId'] = self.script_id.to_json()
        if self.url is not None:
            d['url'] = self.url
        if self.stack_trace is not None:
            d['stackTrace'] = self.stack_trace.to_json()
        if self.exception is not None:
            d['exception'] = self.exception.to_json()
        if self.execution_context_id is not None:
            d['executionContextId'] = self.execution_context_id.to_json()
        if self.exception_meta_data is not None:
            d['exceptionMetaData'] = self.exception_meta_data
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ExceptionDetails:
        return cls(
            exception_id=int(data['exceptionId']),
            text=str(data['text']),
            line_number=int(data['lineNumber']),
            column_number=int(data['columnNumber']),
            script_id=ScriptId.from_json(data['scriptId']) if 'scriptId' in data else None,
            url=str(data['url']) if 'url' in data else None,
            stack_trace=StackTrace.from_json(data['stackTrace']) if 'stackTrace' in data else None,
            exception=RemoteObject.from_json(data['exception']) if 'exception' in data else None,
            execution_context_id=ExecutionContextId.from_json(data['executionContextId']) if 'executionContextId' in data else None,
            exception_meta_data=data['exceptionMetaData'] if 'exceptionMetaData' in data else None,
        )


class Timestamp(float):
    """CDP type alias."""

    def to_json(self) -> float:
        return float(self)

    @classmethod
    def from_json(cls, val: float) -> Timestamp:
        return cls(val)


class TimeDelta(float):
    """CDP type alias."""

    def to_json(self) -> float:
        return float(self)

    @classmethod
    def from_json(cls, val: float) -> TimeDelta:
        return cls(val)


@dataclass
class CallFrame:
    function_name: str
    script_id: ScriptId
    url: str
    line_number: int
    column_number: int

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['functionName'] = function_name
        d['scriptId'] = script_id.to_json()
        d['url'] = url
        d['lineNumber'] = line_number
        d['columnNumber'] = column_number
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CallFrame:
        return cls(
            function_name=str(data['functionName']),
            script_id=ScriptId.from_json(data['scriptId']),
            url=str(data['url']),
            line_number=int(data['lineNumber']),
            column_number=int(data['columnNumber']),
        )


@dataclass
class StackTrace:
    call_frames: list[CallFrame]
    description: Optional[str] = None
    parent: Optional[StackTrace] = None
    parent_id: Optional[StackTraceId] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['callFrames'] = [i.to_json() for i in call_frames]
        if self.description is not None:
            d['description'] = self.description
        if self.parent is not None:
            d['parent'] = self.parent.to_json()
        if self.parent_id is not None:
            d['parentId'] = self.parent_id.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> StackTrace:
        return cls(
            call_frames=[CallFrame.from_json(i) for i in data['callFrames']],
            description=str(data['description']) if 'description' in data else None,
            parent=StackTrace.from_json(data['parent']) if 'parent' in data else None,
            parent_id=StackTraceId.from_json(data['parentId']) if 'parentId' in data else None,
        )


class UniqueDebuggerId(str):
    """CDP string type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> UniqueDebuggerId:
        return cls(val)


@dataclass
class StackTraceId:
    id: str
    debugger_id: Optional[UniqueDebuggerId] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['id'] = id
        if self.debugger_id is not None:
            d['debuggerId'] = self.debugger_id.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> StackTraceId:
        return cls(
            id=str(data['id']),
            debugger_id=UniqueDebuggerId.from_json(data['debuggerId']) if 'debuggerId' in data else None,
        )


@dataclass
class AwaitPromiseResult:
    result: RemoteObject
    exception_details: Optional[ExceptionDetails] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> AwaitPromiseResult:
        return cls(
            result=RemoteObject.from_json(data['result']),
            exception_details=ExceptionDetails.from_json(data['exceptionDetails']) if 'exceptionDetails' in data else None,
        )


def await_promise(promise_object_id: RemoteObjectId, return_by_value: Optional[bool] = None, generate_preview: Optional[bool] = None) -> tuple[T_JSON_DICT, type[AwaitPromiseResult]]:
    params: T_JSON_DICT = {}
    params['promiseObjectId'] = promise_object_id.to_json()
    if return_by_value is not None:
        params['returnByValue'] = return_by_value
    if generate_preview is not None:
        params['generatePreview'] = generate_preview
    cmd: T_JSON_DICT = {"method": "Runtime.awaitPromise", "params": params}
    return cmd, AwaitPromiseResult


@dataclass
class CallFunctionOnResult:
    result: RemoteObject
    exception_details: Optional[ExceptionDetails] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CallFunctionOnResult:
        return cls(
            result=RemoteObject.from_json(data['result']),
            exception_details=ExceptionDetails.from_json(data['exceptionDetails']) if 'exceptionDetails' in data else None,
        )


def call_function_on(function_declaration: str, object_id: Optional[RemoteObjectId] = None, arguments: Optional[list[CallArgument]] = None, silent: Optional[bool] = None, return_by_value: Optional[bool] = None, generate_preview: Optional[bool] = None, user_gesture: Optional[bool] = None, await_promise: Optional[bool] = None, execution_context_id: Optional[ExecutionContextId] = None, object_group: Optional[str] = None, throw_on_side_effect: Optional[bool] = None, unique_context_id: Optional[str] = None, serialization_options: Optional[SerializationOptions] = None) -> tuple[T_JSON_DICT, type[CallFunctionOnResult]]:
    params: T_JSON_DICT = {}
    params['functionDeclaration'] = function_declaration
    if object_id is not None:
        params['objectId'] = object_id.to_json()
    if arguments is not None:
        params['arguments'] = [i.to_json() for i in arguments]
    if silent is not None:
        params['silent'] = silent
    if return_by_value is not None:
        params['returnByValue'] = return_by_value
    if generate_preview is not None:
        params['generatePreview'] = generate_preview
    if user_gesture is not None:
        params['userGesture'] = user_gesture
    if await_promise is not None:
        params['awaitPromise'] = await_promise
    if execution_context_id is not None:
        params['executionContextId'] = execution_context_id.to_json()
    if object_group is not None:
        params['objectGroup'] = object_group
    if throw_on_side_effect is not None:
        params['throwOnSideEffect'] = throw_on_side_effect
    if unique_context_id is not None:
        params['uniqueContextId'] = unique_context_id
    if serialization_options is not None:
        params['serializationOptions'] = serialization_options.to_json()
    cmd: T_JSON_DICT = {"method": "Runtime.callFunctionOn", "params": params}
    return cmd, CallFunctionOnResult


@dataclass
class CompileScriptResult:
    script_id: Optional[ScriptId] = None
    exception_details: Optional[ExceptionDetails] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CompileScriptResult:
        return cls(
            script_id=ScriptId.from_json(data['scriptId']) if 'scriptId' in data else None,
            exception_details=ExceptionDetails.from_json(data['exceptionDetails']) if 'exceptionDetails' in data else None,
        )


def compile_script(expression: str, source_url: str, persist_script: bool, execution_context_id: Optional[ExecutionContextId] = None) -> tuple[T_JSON_DICT, type[CompileScriptResult]]:
    params: T_JSON_DICT = {}
    params['expression'] = expression
    params['sourceURL'] = source_url
    params['persistScript'] = persist_script
    if execution_context_id is not None:
        params['executionContextId'] = execution_context_id.to_json()
    cmd: T_JSON_DICT = {"method": "Runtime.compileScript", "params": params}
    return cmd, CompileScriptResult


def disable() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Runtime.disable", "params": params}
    return cmd, None


def discard_console_entries() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Runtime.discardConsoleEntries", "params": params}
    return cmd, None


def enable() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Runtime.enable", "params": params}
    return cmd, None


@dataclass
class EvaluateResult:
    result: RemoteObject
    exception_details: Optional[ExceptionDetails] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> EvaluateResult:
        return cls(
            result=RemoteObject.from_json(data['result']),
            exception_details=ExceptionDetails.from_json(data['exceptionDetails']) if 'exceptionDetails' in data else None,
        )


def evaluate(expression: str, object_group: Optional[str] = None, include_command_line_api: Optional[bool] = None, silent: Optional[bool] = None, context_id: Optional[ExecutionContextId] = None, return_by_value: Optional[bool] = None, generate_preview: Optional[bool] = None, user_gesture: Optional[bool] = None, await_promise: Optional[bool] = None, throw_on_side_effect: Optional[bool] = None, timeout: Optional[TimeDelta] = None, disable_breaks: Optional[bool] = None, repl_mode: Optional[bool] = None, allow_unsafe_eval_blocked_by_csp: Optional[bool] = None, unique_context_id: Optional[str] = None, serialization_options: Optional[SerializationOptions] = None) -> tuple[T_JSON_DICT, type[EvaluateResult]]:
    params: T_JSON_DICT = {}
    params['expression'] = expression
    if object_group is not None:
        params['objectGroup'] = object_group
    if include_command_line_api is not None:
        params['includeCommandLineAPI'] = include_command_line_api
    if silent is not None:
        params['silent'] = silent
    if context_id is not None:
        params['contextId'] = context_id.to_json()
    if return_by_value is not None:
        params['returnByValue'] = return_by_value
    if generate_preview is not None:
        params['generatePreview'] = generate_preview
    if user_gesture is not None:
        params['userGesture'] = user_gesture
    if await_promise is not None:
        params['awaitPromise'] = await_promise
    if throw_on_side_effect is not None:
        params['throwOnSideEffect'] = throw_on_side_effect
    if timeout is not None:
        params['timeout'] = timeout.to_json()
    if disable_breaks is not None:
        params['disableBreaks'] = disable_breaks
    if repl_mode is not None:
        params['replMode'] = repl_mode
    if allow_unsafe_eval_blocked_by_csp is not None:
        params['allowUnsafeEvalBlockedByCSP'] = allow_unsafe_eval_blocked_by_csp
    if unique_context_id is not None:
        params['uniqueContextId'] = unique_context_id
    if serialization_options is not None:
        params['serializationOptions'] = serialization_options.to_json()
    cmd: T_JSON_DICT = {"method": "Runtime.evaluate", "params": params}
    return cmd, EvaluateResult


@dataclass
class GetIsolateIdResult:
    id: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetIsolateIdResult:
        return cls(
            id=str(data['id']),
        )


def get_isolate_id() -> tuple[T_JSON_DICT, type[GetIsolateIdResult]]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Runtime.getIsolateId", "params": params}
    return cmd, GetIsolateIdResult


@dataclass
class GetHeapUsageResult:
    used_size: float
    total_size: float
    embedder_heap_used_size: float
    backing_storage_size: float

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetHeapUsageResult:
        return cls(
            used_size=float(data['usedSize']),
            total_size=float(data['totalSize']),
            embedder_heap_used_size=float(data['embedderHeapUsedSize']),
            backing_storage_size=float(data['backingStorageSize']),
        )


def get_heap_usage() -> tuple[T_JSON_DICT, type[GetHeapUsageResult]]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Runtime.getHeapUsage", "params": params}
    return cmd, GetHeapUsageResult


@dataclass
class GetPropertiesResult:
    result: list[PropertyDescriptor]
    internal_properties: Optional[list[InternalPropertyDescriptor]] = None
    private_properties: Optional[list[PrivatePropertyDescriptor]] = None
    exception_details: Optional[ExceptionDetails] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetPropertiesResult:
        return cls(
            result=[PropertyDescriptor.from_json(i) for i in data['result']],
            internal_properties=[InternalPropertyDescriptor.from_json(i) for i in data['internalProperties']] if 'internalProperties' in data else None,
            private_properties=[PrivatePropertyDescriptor.from_json(i) for i in data['privateProperties']] if 'privateProperties' in data else None,
            exception_details=ExceptionDetails.from_json(data['exceptionDetails']) if 'exceptionDetails' in data else None,
        )


def get_properties(object_id: RemoteObjectId, own_properties: Optional[bool] = None, accessor_properties_only: Optional[bool] = None, generate_preview: Optional[bool] = None, non_indexed_properties_only: Optional[bool] = None) -> tuple[T_JSON_DICT, type[GetPropertiesResult]]:
    params: T_JSON_DICT = {}
    params['objectId'] = object_id.to_json()
    if own_properties is not None:
        params['ownProperties'] = own_properties
    if accessor_properties_only is not None:
        params['accessorPropertiesOnly'] = accessor_properties_only
    if generate_preview is not None:
        params['generatePreview'] = generate_preview
    if non_indexed_properties_only is not None:
        params['nonIndexedPropertiesOnly'] = non_indexed_properties_only
    cmd: T_JSON_DICT = {"method": "Runtime.getProperties", "params": params}
    return cmd, GetPropertiesResult


@dataclass
class GlobalLexicalScopeNamesResult:
    names: list[str]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GlobalLexicalScopeNamesResult:
        return cls(
            names=[str(i) for i in data['names']],
        )


def global_lexical_scope_names(execution_context_id: Optional[ExecutionContextId] = None) -> tuple[T_JSON_DICT, type[GlobalLexicalScopeNamesResult]]:
    params: T_JSON_DICT = {}
    if execution_context_id is not None:
        params['executionContextId'] = execution_context_id.to_json()
    cmd: T_JSON_DICT = {"method": "Runtime.globalLexicalScopeNames", "params": params}
    return cmd, GlobalLexicalScopeNamesResult


@dataclass
class QueryObjectsResult:
    objects: RemoteObject

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> QueryObjectsResult:
        return cls(
            objects=RemoteObject.from_json(data['objects']),
        )


def query_objects(prototype_object_id: RemoteObjectId, object_group: Optional[str] = None) -> tuple[T_JSON_DICT, type[QueryObjectsResult]]:
    params: T_JSON_DICT = {}
    params['prototypeObjectId'] = prototype_object_id.to_json()
    if object_group is not None:
        params['objectGroup'] = object_group
    cmd: T_JSON_DICT = {"method": "Runtime.queryObjects", "params": params}
    return cmd, QueryObjectsResult


def release_object(object_id: RemoteObjectId) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['objectId'] = object_id.to_json()
    cmd: T_JSON_DICT = {"method": "Runtime.releaseObject", "params": params}
    return cmd, None


def release_object_group(object_group: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['objectGroup'] = object_group
    cmd: T_JSON_DICT = {"method": "Runtime.releaseObjectGroup", "params": params}
    return cmd, None


def run_if_waiting_for_debugger() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Runtime.runIfWaitingForDebugger", "params": params}
    return cmd, None


@dataclass
class RunScriptResult:
    result: RemoteObject
    exception_details: Optional[ExceptionDetails] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> RunScriptResult:
        return cls(
            result=RemoteObject.from_json(data['result']),
            exception_details=ExceptionDetails.from_json(data['exceptionDetails']) if 'exceptionDetails' in data else None,
        )


def run_script(script_id: ScriptId, execution_context_id: Optional[ExecutionContextId] = None, object_group: Optional[str] = None, silent: Optional[bool] = None, include_command_line_api: Optional[bool] = None, return_by_value: Optional[bool] = None, generate_preview: Optional[bool] = None, await_promise: Optional[bool] = None) -> tuple[T_JSON_DICT, type[RunScriptResult]]:
    params: T_JSON_DICT = {}
    params['scriptId'] = script_id.to_json()
    if execution_context_id is not None:
        params['executionContextId'] = execution_context_id.to_json()
    if object_group is not None:
        params['objectGroup'] = object_group
    if silent is not None:
        params['silent'] = silent
    if include_command_line_api is not None:
        params['includeCommandLineAPI'] = include_command_line_api
    if return_by_value is not None:
        params['returnByValue'] = return_by_value
    if generate_preview is not None:
        params['generatePreview'] = generate_preview
    if await_promise is not None:
        params['awaitPromise'] = await_promise
    cmd: T_JSON_DICT = {"method": "Runtime.runScript", "params": params}
    return cmd, RunScriptResult


def set_async_call_stack_depth(max_depth: int) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['maxDepth'] = max_depth
    cmd: T_JSON_DICT = {"method": "Runtime.setAsyncCallStackDepth", "params": params}
    return cmd, None


def set_custom_object_formatter_enabled(enabled: bool) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['enabled'] = enabled
    cmd: T_JSON_DICT = {"method": "Runtime.setCustomObjectFormatterEnabled", "params": params}
    return cmd, None


def set_max_call_stack_size_to_capture(size: int) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['size'] = size
    cmd: T_JSON_DICT = {"method": "Runtime.setMaxCallStackSizeToCapture", "params": params}
    return cmd, None


def terminate_execution() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Runtime.terminateExecution", "params": params}
    return cmd, None


def add_binding(name: str, execution_context_id: Optional[ExecutionContextId] = None, execution_context_name: Optional[str] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['name'] = name
    if execution_context_id is not None:
        params['executionContextId'] = execution_context_id.to_json()
    if execution_context_name is not None:
        params['executionContextName'] = execution_context_name
    cmd: T_JSON_DICT = {"method": "Runtime.addBinding", "params": params}
    return cmd, None


def remove_binding(name: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['name'] = name
    cmd: T_JSON_DICT = {"method": "Runtime.removeBinding", "params": params}
    return cmd, None


@dataclass
class GetExceptionDetailsResult:
    exception_details: Optional[ExceptionDetails] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetExceptionDetailsResult:
        return cls(
            exception_details=ExceptionDetails.from_json(data['exceptionDetails']) if 'exceptionDetails' in data else None,
        )


def get_exception_details(error_object_id: RemoteObjectId) -> tuple[T_JSON_DICT, type[GetExceptionDetailsResult]]:
    params: T_JSON_DICT = {}
    params['errorObjectId'] = error_object_id.to_json()
    cmd: T_JSON_DICT = {"method": "Runtime.getExceptionDetails", "params": params}
    return cmd, GetExceptionDetailsResult


@dataclass
class BindingCalled:
    EVENT_NAME: str = field(init=False, repr=False, default="Runtime.bindingCalled")
    name: str
    payload: str
    execution_context_id: ExecutionContextId

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> BindingCalled:
        return cls(
            name=str(data['name']),
            payload=str(data['payload']),
            execution_context_id=ExecutionContextId.from_json(data['executionContextId']),
        )


@dataclass
class ConsoleAPICalled:
    EVENT_NAME: str = field(init=False, repr=False, default="Runtime.consoleAPICalled")
    type: str
    args: list[RemoteObject]
    execution_context_id: ExecutionContextId
    timestamp: Timestamp
    stack_trace: Optional[StackTrace] = None
    context: Optional[str] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ConsoleAPICalled:
        return cls(
            type=str(data['type']),
            args=[RemoteObject.from_json(i) for i in data['args']],
            execution_context_id=ExecutionContextId.from_json(data['executionContextId']),
            timestamp=Timestamp.from_json(data['timestamp']),
            stack_trace=StackTrace.from_json(data['stackTrace']) if 'stackTrace' in data else None,
            context=str(data['context']) if 'context' in data else None,
        )


@dataclass
class ExceptionRevoked:
    EVENT_NAME: str = field(init=False, repr=False, default="Runtime.exceptionRevoked")
    reason: str
    exception_id: int

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ExceptionRevoked:
        return cls(
            reason=str(data['reason']),
            exception_id=int(data['exceptionId']),
        )


@dataclass
class ExceptionThrown:
    EVENT_NAME: str = field(init=False, repr=False, default="Runtime.exceptionThrown")
    timestamp: Timestamp
    exception_details: ExceptionDetails

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ExceptionThrown:
        return cls(
            timestamp=Timestamp.from_json(data['timestamp']),
            exception_details=ExceptionDetails.from_json(data['exceptionDetails']),
        )


@dataclass
class ExecutionContextCreated:
    EVENT_NAME: str = field(init=False, repr=False, default="Runtime.executionContextCreated")
    context: ExecutionContextDescription

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ExecutionContextCreated:
        return cls(
            context=ExecutionContextDescription.from_json(data['context']),
        )


@dataclass
class ExecutionContextDestroyed:
    EVENT_NAME: str = field(init=False, repr=False, default="Runtime.executionContextDestroyed")
    execution_context_id: ExecutionContextId
    execution_context_unique_id: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ExecutionContextDestroyed:
        return cls(
            execution_context_id=ExecutionContextId.from_json(data['executionContextId']),
            execution_context_unique_id=str(data['executionContextUniqueId']),
        )


@dataclass
class ExecutionContextsCleared:
    EVENT_NAME: str = field(init=False, repr=False, default="Runtime.executionContextsCleared")

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ExecutionContextsCleared:
        return cls()


@dataclass
class InspectRequested:
    EVENT_NAME: str = field(init=False, repr=False, default="Runtime.inspectRequested")
    object: RemoteObject
    hints: T_JSON_DICT
    execution_context_id: Optional[ExecutionContextId] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> InspectRequested:
        return cls(
            object=RemoteObject.from_json(data['object']),
            hints=data['hints'],
            execution_context_id=ExecutionContextId.from_json(data['executionContextId']) if 'executionContextId' in data else None,
        )

