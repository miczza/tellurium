"""Auto-generated CDP bindings for the Accessibility domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from tellurium.cdp.types import T_JSON_DICT


class AXNodeId(str):
    """CDP string type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> AXNodeId:
        return cls(val)


class AXValueType(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> AXValueType:
        return cls(val)


class AXValueSourceType(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> AXValueSourceType:
        return cls(val)


class AXValueNativeSourceType(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> AXValueNativeSourceType:
        return cls(val)


@dataclass
class AXValueSource:
    type: AXValueSourceType
    value: Optional[AXValue] = None
    attribute: Optional[str] = None
    attribute_value: Optional[AXValue] = None
    superseded: Optional[bool] = None
    native_source: Optional[AXValueNativeSourceType] = None
    native_source_value: Optional[AXValue] = None
    invalid: Optional[bool] = None
    invalid_reason: Optional[str] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['type'] = type.to_json()
        if self.value is not None:
            d['value'] = self.value.to_json()
        if self.attribute is not None:
            d['attribute'] = self.attribute
        if self.attribute_value is not None:
            d['attributeValue'] = self.attribute_value.to_json()
        if self.superseded is not None:
            d['superseded'] = self.superseded
        if self.native_source is not None:
            d['nativeSource'] = self.native_source.to_json()
        if self.native_source_value is not None:
            d['nativeSourceValue'] = self.native_source_value.to_json()
        if self.invalid is not None:
            d['invalid'] = self.invalid
        if self.invalid_reason is not None:
            d['invalidReason'] = self.invalid_reason
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> AXValueSource:
        return cls(
            type=AXValueSourceType.from_json(data['type']),
            value=AXValue.from_json(data['value']) if 'value' in data else None,
            attribute=str(data['attribute']) if 'attribute' in data else None,
            attribute_value=AXValue.from_json(data['attributeValue']) if 'attributeValue' in data else None,
            superseded=bool(data['superseded']) if 'superseded' in data else None,
            native_source=AXValueNativeSourceType.from_json(data['nativeSource']) if 'nativeSource' in data else None,
            native_source_value=AXValue.from_json(data['nativeSourceValue']) if 'nativeSourceValue' in data else None,
            invalid=bool(data['invalid']) if 'invalid' in data else None,
            invalid_reason=str(data['invalidReason']) if 'invalidReason' in data else None,
        )


@dataclass
class AXRelatedNode:
    backend_dom_node_id: BackendNodeId
    idref: Optional[str] = None
    text: Optional[str] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['backendDOMNodeId'] = backend_dom_node_id.to_json()
        if self.idref is not None:
            d['idref'] = self.idref
        if self.text is not None:
            d['text'] = self.text
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> AXRelatedNode:
        return cls(
            backend_dom_node_id=BackendNodeId.from_json(data['backendDOMNodeId']),
            idref=str(data['idref']) if 'idref' in data else None,
            text=str(data['text']) if 'text' in data else None,
        )


@dataclass
class AXProperty:
    name: AXPropertyName
    value: AXValue

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['name'] = name.to_json()
        d['value'] = value.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> AXProperty:
        return cls(
            name=AXPropertyName.from_json(data['name']),
            value=AXValue.from_json(data['value']),
        )


@dataclass
class AXValue:
    type: AXValueType
    value: Optional[Any] = None
    related_nodes: Optional[list[AXRelatedNode]] = None
    sources: Optional[list[AXValueSource]] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['type'] = type.to_json()
        if self.value is not None:
            d['value'] = self.value
        if self.related_nodes is not None:
            d['relatedNodes'] = [i.to_json() for i in self.related_nodes]
        if self.sources is not None:
            d['sources'] = [i.to_json() for i in self.sources]
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> AXValue:
        return cls(
            type=AXValueType.from_json(data['type']),
            value=data['value'] if 'value' in data else None,
            related_nodes=[AXRelatedNode.from_json(i) for i in data['relatedNodes']] if 'relatedNodes' in data else None,
            sources=[AXValueSource.from_json(i) for i in data['sources']] if 'sources' in data else None,
        )


class AXPropertyName(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> AXPropertyName:
        return cls(val)


@dataclass
class AXNode:
    node_id: AXNodeId
    ignored: bool
    ignored_reasons: Optional[list[AXProperty]] = None
    role: Optional[AXValue] = None
    chrome_role: Optional[AXValue] = None
    name: Optional[AXValue] = None
    description: Optional[AXValue] = None
    value: Optional[AXValue] = None
    properties: Optional[list[AXProperty]] = None
    parent_id: Optional[AXNodeId] = None
    child_ids: Optional[list[AXNodeId]] = None
    backend_dom_node_id: Optional[BackendNodeId] = None
    frame_id: Optional[FrameId] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['nodeId'] = node_id.to_json()
        d['ignored'] = ignored
        if self.ignored_reasons is not None:
            d['ignoredReasons'] = [i.to_json() for i in self.ignored_reasons]
        if self.role is not None:
            d['role'] = self.role.to_json()
        if self.chrome_role is not None:
            d['chromeRole'] = self.chrome_role.to_json()
        if self.name is not None:
            d['name'] = self.name.to_json()
        if self.description is not None:
            d['description'] = self.description.to_json()
        if self.value is not None:
            d['value'] = self.value.to_json()
        if self.properties is not None:
            d['properties'] = [i.to_json() for i in self.properties]
        if self.parent_id is not None:
            d['parentId'] = self.parent_id.to_json()
        if self.child_ids is not None:
            d['childIds'] = [i.to_json() for i in self.child_ids]
        if self.backend_dom_node_id is not None:
            d['backendDOMNodeId'] = self.backend_dom_node_id.to_json()
        if self.frame_id is not None:
            d['frameId'] = self.frame_id.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> AXNode:
        return cls(
            node_id=AXNodeId.from_json(data['nodeId']),
            ignored=bool(data['ignored']),
            ignored_reasons=[AXProperty.from_json(i) for i in data['ignoredReasons']] if 'ignoredReasons' in data else None,
            role=AXValue.from_json(data['role']) if 'role' in data else None,
            chrome_role=AXValue.from_json(data['chromeRole']) if 'chromeRole' in data else None,
            name=AXValue.from_json(data['name']) if 'name' in data else None,
            description=AXValue.from_json(data['description']) if 'description' in data else None,
            value=AXValue.from_json(data['value']) if 'value' in data else None,
            properties=[AXProperty.from_json(i) for i in data['properties']] if 'properties' in data else None,
            parent_id=AXNodeId.from_json(data['parentId']) if 'parentId' in data else None,
            child_ids=[AXNodeId.from_json(i) for i in data['childIds']] if 'childIds' in data else None,
            backend_dom_node_id=BackendNodeId.from_json(data['backendDOMNodeId']) if 'backendDOMNodeId' in data else None,
            frame_id=FrameId.from_json(data['frameId']) if 'frameId' in data else None,
        )


def disable() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Accessibility.disable", "params": params}
    return cmd, None


def enable() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "Accessibility.enable", "params": params}
    return cmd, None


@dataclass
class GetPartialAXTreeResult:
    nodes: list[AXNode]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetPartialAXTreeResult:
        return cls(
            nodes=[AXNode.from_json(i) for i in data['nodes']],
        )


def get_partial_ax_tree(node_id: Optional[NodeId] = None, backend_node_id: Optional[BackendNodeId] = None, object_id: Optional[RemoteObjectId] = None, fetch_relatives: Optional[bool] = None) -> tuple[T_JSON_DICT, type[GetPartialAXTreeResult]]:
    params: T_JSON_DICT = {}
    if node_id is not None:
        params['nodeId'] = node_id.to_json()
    if backend_node_id is not None:
        params['backendNodeId'] = backend_node_id.to_json()
    if object_id is not None:
        params['objectId'] = object_id.to_json()
    if fetch_relatives is not None:
        params['fetchRelatives'] = fetch_relatives
    cmd: T_JSON_DICT = {"method": "Accessibility.getPartialAXTree", "params": params}
    return cmd, GetPartialAXTreeResult


@dataclass
class GetFullAXTreeResult:
    nodes: list[AXNode]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetFullAXTreeResult:
        return cls(
            nodes=[AXNode.from_json(i) for i in data['nodes']],
        )


def get_full_ax_tree(depth: Optional[int] = None, frame_id: Optional[FrameId] = None) -> tuple[T_JSON_DICT, type[GetFullAXTreeResult]]:
    params: T_JSON_DICT = {}
    if depth is not None:
        params['depth'] = depth
    if frame_id is not None:
        params['frameId'] = frame_id.to_json()
    cmd: T_JSON_DICT = {"method": "Accessibility.getFullAXTree", "params": params}
    return cmd, GetFullAXTreeResult


@dataclass
class GetRootAXNodeResult:
    node: AXNode

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetRootAXNodeResult:
        return cls(
            node=AXNode.from_json(data['node']),
        )


def get_root_ax_node(frame_id: Optional[FrameId] = None) -> tuple[T_JSON_DICT, type[GetRootAXNodeResult]]:
    params: T_JSON_DICT = {}
    if frame_id is not None:
        params['frameId'] = frame_id.to_json()
    cmd: T_JSON_DICT = {"method": "Accessibility.getRootAXNode", "params": params}
    return cmd, GetRootAXNodeResult


@dataclass
class GetAXNodeAndAncestorsResult:
    nodes: list[AXNode]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetAXNodeAndAncestorsResult:
        return cls(
            nodes=[AXNode.from_json(i) for i in data['nodes']],
        )


def get_ax_node_and_ancestors(node_id: Optional[NodeId] = None, backend_node_id: Optional[BackendNodeId] = None, object_id: Optional[RemoteObjectId] = None) -> tuple[T_JSON_DICT, type[GetAXNodeAndAncestorsResult]]:
    params: T_JSON_DICT = {}
    if node_id is not None:
        params['nodeId'] = node_id.to_json()
    if backend_node_id is not None:
        params['backendNodeId'] = backend_node_id.to_json()
    if object_id is not None:
        params['objectId'] = object_id.to_json()
    cmd: T_JSON_DICT = {"method": "Accessibility.getAXNodeAndAncestors", "params": params}
    return cmd, GetAXNodeAndAncestorsResult


@dataclass
class GetChildAXNodesResult:
    nodes: list[AXNode]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetChildAXNodesResult:
        return cls(
            nodes=[AXNode.from_json(i) for i in data['nodes']],
        )


def get_child_ax_nodes(id: AXNodeId, frame_id: Optional[FrameId] = None) -> tuple[T_JSON_DICT, type[GetChildAXNodesResult]]:
    params: T_JSON_DICT = {}
    params['id'] = id.to_json()
    if frame_id is not None:
        params['frameId'] = frame_id.to_json()
    cmd: T_JSON_DICT = {"method": "Accessibility.getChildAXNodes", "params": params}
    return cmd, GetChildAXNodesResult


@dataclass
class QueryAXTreeResult:
    nodes: list[AXNode]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> QueryAXTreeResult:
        return cls(
            nodes=[AXNode.from_json(i) for i in data['nodes']],
        )


def query_ax_tree(node_id: Optional[NodeId] = None, backend_node_id: Optional[BackendNodeId] = None, object_id: Optional[RemoteObjectId] = None, accessible_name: Optional[str] = None, role: Optional[str] = None) -> tuple[T_JSON_DICT, type[QueryAXTreeResult]]:
    params: T_JSON_DICT = {}
    if node_id is not None:
        params['nodeId'] = node_id.to_json()
    if backend_node_id is not None:
        params['backendNodeId'] = backend_node_id.to_json()
    if object_id is not None:
        params['objectId'] = object_id.to_json()
    if accessible_name is not None:
        params['accessibleName'] = accessible_name
    if role is not None:
        params['role'] = role
    cmd: T_JSON_DICT = {"method": "Accessibility.queryAXTree", "params": params}
    return cmd, QueryAXTreeResult


@dataclass
class LoadComplete:
    EVENT_NAME: str = field(init=False, repr=False, default="Accessibility.loadComplete")
    root: AXNode

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> LoadComplete:
        return cls(
            root=AXNode.from_json(data['root']),
        )


@dataclass
class NodesUpdated:
    EVENT_NAME: str = field(init=False, repr=False, default="Accessibility.nodesUpdated")
    nodes: list[AXNode]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> NodesUpdated:
        return cls(
            nodes=[AXNode.from_json(i) for i in data['nodes']],
        )

