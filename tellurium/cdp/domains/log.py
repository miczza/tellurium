"""Auto-generated CDP bindings for the Log domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from tellurium.cdp.types import T_JSON_DICT


@dataclass
class LogEntry:
    source: str
    level: str
    text: str
    timestamp: Timestamp
    category: Optional[str] = None
    url: Optional[str] = None
    line_number: Optional[int] = None
    stack_trace: Optional[StackTrace] = None
    network_request_id: Optional[RequestId] = None
    worker_id: Optional[str] = None
    args: Optional[list[RemoteObject]] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['source'] = source
        d['level'] = level
        d['text'] = text
        d['timestamp'] = timestamp.to_json()
        if self.category is not None:
            d['category'] = self.category
        if self.url is not None:
            d['url'] = self.url
        if self.line_number is not None:
            d['lineNumber'] = self.line_number
        if self.stack_trace is not None:
            d['stackTrace'] = self.stack_trace.to_json()
        if self.network_request_id is not None:
            d['networkRequestId'] = self.network_request_id.to_json()
        if self.worker_id is not None:
            d['workerId'] = self.worker_id
        if self.args is not None:
            d['args'] = [i.to_json() for i in self.args]
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> LogEntry:
        return cls(
            source=str(data['source']),
            level=str(data['level']),
            text=str(data['text']),
            timestamp=Timestamp.from_json(data['timestamp']),
            category=str(data['category']) if 'category' in data else None,
            url=str(data['url']) if 'url' in data else None,
            line_number=int(data['lineNumber']) if 'lineNumber' in data else None,
            stack_trace=StackTrace.from_json(data['stackTrace']) if 'stackTrace' in data else None,
            network_request_id=RequestId.from_json(data['networkRequestId']) if 'networkRequestId' in data else None,
            worker_id=str(data['workerId']) if 'workerId' in data else None,
            args=[RemoteObject.from_json(i) for i in data['args']] if 'args' in data else None,
        )


@dataclass
class ViolationSetting:
    name: str
    threshold: float

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['name'] = name
        d['threshold'] = threshold
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ViolationSetting:
        return cls(
            name=str(data['name']),
            threshold=float(data['threshold']),
        )


def clear() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Log.clear", "params": params}
    return cmd, None


def disable() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Log.disable", "params": params}
    return cmd, None


def enable() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Log.enable", "params": params}
    return cmd, None


def start_violations_report(config: list[ViolationSetting]) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['config'] = [i.to_json() for i in config]
    cmd: T_JSON_DICT = {"method": "Log.startViolationsReport", "params": params}
    return cmd, None


def stop_violations_report() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Log.stopViolationsReport", "params": params}
    return cmd, None


@dataclass
class EntryAdded:
    EVENT_NAME: str = field(init=False, repr=False, default="Log.entryAdded")
    entry: LogEntry

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> EntryAdded:
        return cls(
            entry=LogEntry.from_json(data['entry']),
        )

