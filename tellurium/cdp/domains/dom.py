"""Auto-generated CDP bindings for the DOM domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from tellurium.cdp.types import T_JSON_DICT


class NodeId(int):
    """CDP type alias."""

    def to_json(self) -> int:
        return int(self)

    @classmethod
    def from_json(cls, val: int) -> NodeId:
        return cls(val)


class BackendNodeId(int):
    """CDP type alias."""

    def to_json(self) -> int:
        return int(self)

    @classmethod
    def from_json(cls, val: int) -> BackendNodeId:
        return cls(val)


class StyleSheetId(str):
    """CDP string type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> StyleSheetId:
        return cls(val)


@dataclass
class BackendNode:
    node_type: int
    node_name: str
    backend_node_id: BackendNodeId

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['nodeType'] = node_type
        d['nodeName'] = node_name
        d['backendNodeId'] = backend_node_id.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> BackendNode:
        return cls(
            node_type=int(data['nodeType']),
            node_name=str(data['nodeName']),
            backend_node_id=BackendNodeId.from_json(data['backendNodeId']),
        )


class PseudoType(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> PseudoType:
        return cls(val)


class ShadowRootType(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> ShadowRootType:
        return cls(val)


class CompatibilityMode(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> CompatibilityMode:
        return cls(val)


class PhysicalAxes(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> PhysicalAxes:
        return cls(val)


class LogicalAxes(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> LogicalAxes:
        return cls(val)


class ScrollOrientation(str):
    """CDP type alias."""

    def to_json(self) -> str:
        return str(self)

    @classmethod
    def from_json(cls, val: str) -> ScrollOrientation:
        return cls(val)


@dataclass
class Node:
    node_id: NodeId
    backend_node_id: BackendNodeId
    node_type: int
    node_name: str
    local_name: str
    node_value: str
    parent_id: Optional[NodeId] = None
    child_node_count: Optional[int] = None
    children: Optional[list[Node]] = None
    attributes: Optional[list[str]] = None
    document_url: Optional[str] = None
    base_url: Optional[str] = None
    public_id: Optional[str] = None
    system_id: Optional[str] = None
    internal_subset: Optional[str] = None
    xml_version: Optional[str] = None
    name: Optional[str] = None
    value: Optional[str] = None
    pseudo_type: Optional[PseudoType] = None
    pseudo_identifier: Optional[str] = None
    shadow_root_type: Optional[ShadowRootType] = None
    frame_id: Optional[FrameId] = None
    content_document: Optional[Node] = None
    shadow_roots: Optional[list[Node]] = None
    template_content: Optional[Node] = None
    pseudo_elements: Optional[list[Node]] = None
    imported_document: Optional[Node] = None
    distributed_nodes: Optional[list[BackendNode]] = None
    is_svg: Optional[bool] = None
    compatibility_mode: Optional[CompatibilityMode] = None
    assigned_slot: Optional[BackendNode] = None
    is_scrollable: Optional[bool] = None
    affected_by_starting_styles: Optional[bool] = None
    adopted_style_sheets: Optional[list[StyleSheetId]] = None
    ad_provenance: Optional[AdProvenance] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['nodeId'] = node_id.to_json()
        d['backendNodeId'] = backend_node_id.to_json()
        d['nodeType'] = node_type
        d['nodeName'] = node_name
        d['localName'] = local_name
        d['nodeValue'] = node_value
        if self.parent_id is not None:
            d['parentId'] = self.parent_id.to_json()
        if self.child_node_count is not None:
            d['childNodeCount'] = self.child_node_count
        if self.children is not None:
            d['children'] = [i.to_json() for i in self.children]
        if self.attributes is not None:
            d['attributes'] = list(self.attributes)
        if self.document_url is not None:
            d['documentURL'] = self.document_url
        if self.base_url is not None:
            d['baseURL'] = self.base_url
        if self.public_id is not None:
            d['publicId'] = self.public_id
        if self.system_id is not None:
            d['systemId'] = self.system_id
        if self.internal_subset is not None:
            d['internalSubset'] = self.internal_subset
        if self.xml_version is not None:
            d['xmlVersion'] = self.xml_version
        if self.name is not None:
            d['name'] = self.name
        if self.value is not None:
            d['value'] = self.value
        if self.pseudo_type is not None:
            d['pseudoType'] = self.pseudo_type.to_json()
        if self.pseudo_identifier is not None:
            d['pseudoIdentifier'] = self.pseudo_identifier
        if self.shadow_root_type is not None:
            d['shadowRootType'] = self.shadow_root_type.to_json()
        if self.frame_id is not None:
            d['frameId'] = self.frame_id.to_json()
        if self.content_document is not None:
            d['contentDocument'] = self.content_document.to_json()
        if self.shadow_roots is not None:
            d['shadowRoots'] = [i.to_json() for i in self.shadow_roots]
        if self.template_content is not None:
            d['templateContent'] = self.template_content.to_json()
        if self.pseudo_elements is not None:
            d['pseudoElements'] = [i.to_json() for i in self.pseudo_elements]
        if self.imported_document is not None:
            d['importedDocument'] = self.imported_document.to_json()
        if self.distributed_nodes is not None:
            d['distributedNodes'] = [i.to_json() for i in self.distributed_nodes]
        if self.is_svg is not None:
            d['isSVG'] = self.is_svg
        if self.compatibility_mode is not None:
            d['compatibilityMode'] = self.compatibility_mode.to_json()
        if self.assigned_slot is not None:
            d['assignedSlot'] = self.assigned_slot.to_json()
        if self.is_scrollable is not None:
            d['isScrollable'] = self.is_scrollable
        if self.affected_by_starting_styles is not None:
            d['affectedByStartingStyles'] = self.affected_by_starting_styles
        if self.adopted_style_sheets is not None:
            d['adoptedStyleSheets'] = [i.to_json() for i in self.adopted_style_sheets]
        if self.ad_provenance is not None:
            d['adProvenance'] = self.ad_provenance.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> Node:
        return cls(
            node_id=NodeId.from_json(data['nodeId']),
            backend_node_id=BackendNodeId.from_json(data['backendNodeId']),
            node_type=int(data['nodeType']),
            node_name=str(data['nodeName']),
            local_name=str(data['localName']),
            node_value=str(data['nodeValue']),
            parent_id=NodeId.from_json(data['parentId']) if 'parentId' in data else None,
            child_node_count=int(data['childNodeCount']) if 'childNodeCount' in data else None,
            children=[Node.from_json(i) for i in data['children']] if 'children' in data else None,
            attributes=[str(i) for i in data['attributes']] if 'attributes' in data else None,
            document_url=str(data['documentURL']) if 'documentURL' in data else None,
            base_url=str(data['baseURL']) if 'baseURL' in data else None,
            public_id=str(data['publicId']) if 'publicId' in data else None,
            system_id=str(data['systemId']) if 'systemId' in data else None,
            internal_subset=str(data['internalSubset']) if 'internalSubset' in data else None,
            xml_version=str(data['xmlVersion']) if 'xmlVersion' in data else None,
            name=str(data['name']) if 'name' in data else None,
            value=str(data['value']) if 'value' in data else None,
            pseudo_type=PseudoType.from_json(data['pseudoType']) if 'pseudoType' in data else None,
            pseudo_identifier=str(data['pseudoIdentifier']) if 'pseudoIdentifier' in data else None,
            shadow_root_type=ShadowRootType.from_json(data['shadowRootType']) if 'shadowRootType' in data else None,
            frame_id=FrameId.from_json(data['frameId']) if 'frameId' in data else None,
            content_document=Node.from_json(data['contentDocument']) if 'contentDocument' in data else None,
            shadow_roots=[Node.from_json(i) for i in data['shadowRoots']] if 'shadowRoots' in data else None,
            template_content=Node.from_json(data['templateContent']) if 'templateContent' in data else None,
            pseudo_elements=[Node.from_json(i) for i in data['pseudoElements']] if 'pseudoElements' in data else None,
            imported_document=Node.from_json(data['importedDocument']) if 'importedDocument' in data else None,
            distributed_nodes=[BackendNode.from_json(i) for i in data['distributedNodes']] if 'distributedNodes' in data else None,
            is_svg=bool(data['isSVG']) if 'isSVG' in data else None,
            compatibility_mode=CompatibilityMode.from_json(data['compatibilityMode']) if 'compatibilityMode' in data else None,
            assigned_slot=BackendNode.from_json(data['assignedSlot']) if 'assignedSlot' in data else None,
            is_scrollable=bool(data['isScrollable']) if 'isScrollable' in data else None,
            affected_by_starting_styles=bool(data['affectedByStartingStyles']) if 'affectedByStartingStyles' in data else None,
            adopted_style_sheets=[StyleSheetId.from_json(i) for i in data['adoptedStyleSheets']] if 'adoptedStyleSheets' in data else None,
            ad_provenance=AdProvenance.from_json(data['adProvenance']) if 'adProvenance' in data else None,
        )


@dataclass
class DetachedElementInfo:
    tree_node: Node
    retained_node_ids: list[NodeId]

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['treeNode'] = tree_node.to_json()
        d['retainedNodeIds'] = [i.to_json() for i in retained_node_ids]
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DetachedElementInfo:
        return cls(
            tree_node=Node.from_json(data['treeNode']),
            retained_node_ids=[NodeId.from_json(i) for i in data['retainedNodeIds']],
        )


@dataclass
class RGBA:
    r: int
    g: int
    b: int
    a: Optional[float] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['r'] = r
        d['g'] = g
        d['b'] = b
        if self.a is not None:
            d['a'] = self.a
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> RGBA:
        return cls(
            r=int(data['r']),
            g=int(data['g']),
            b=int(data['b']),
            a=float(data['a']) if 'a' in data else None,
        )


class Quad(Any):
    """CDP type alias."""

    def to_json(self) -> Any:
        return Any(self)

    @classmethod
    def from_json(cls, val: Any) -> Quad:
        return cls(val)


@dataclass
class BoxModel:
    content: Quad
    padding: Quad
    border: Quad
    margin: Quad
    width: int
    height: int
    shape_outside: Optional[ShapeOutsideInfo] = None

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['content'] = content.to_json()
        d['padding'] = padding.to_json()
        d['border'] = border.to_json()
        d['margin'] = margin.to_json()
        d['width'] = width
        d['height'] = height
        if self.shape_outside is not None:
            d['shapeOutside'] = self.shape_outside.to_json()
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> BoxModel:
        return cls(
            content=Quad.from_json(data['content']),
            padding=Quad.from_json(data['padding']),
            border=Quad.from_json(data['border']),
            margin=Quad.from_json(data['margin']),
            width=int(data['width']),
            height=int(data['height']),
            shape_outside=ShapeOutsideInfo.from_json(data['shapeOutside']) if 'shapeOutside' in data else None,
        )


@dataclass
class ShapeOutsideInfo:
    bounds: Quad
    shape: list[Any]
    margin_shape: list[Any]

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['bounds'] = bounds.to_json()
        d['shape'] = list(shape)
        d['marginShape'] = list(margin_shape)
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ShapeOutsideInfo:
        return cls(
            bounds=Quad.from_json(data['bounds']),
            shape=list(data['shape']),
            margin_shape=list(data['marginShape']),
        )


@dataclass
class Rect:
    x: float
    y: float
    width: float
    height: float

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['x'] = x
        d['y'] = y
        d['width'] = width
        d['height'] = height
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> Rect:
        return cls(
            x=float(data['x']),
            y=float(data['y']),
            width=float(data['width']),
            height=float(data['height']),
        )


@dataclass
class CSSComputedStyleProperty:
    name: str
    value: str

    def to_json(self) -> T_JSON_DICT:
        d: T_JSON_DICT = {}
        d['name'] = name
        d['value'] = value
        return d

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CSSComputedStyleProperty:
        return cls(
            name=str(data['name']),
            value=str(data['value']),
        )


@dataclass
class CollectClassNamesFromSubtreeResult:
    class_names: list[str]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CollectClassNamesFromSubtreeResult:
        return cls(
            class_names=[str(i) for i in data['classNames']],
        )


def collect_class_names_from_subtree(node_id: NodeId) -> tuple[T_JSON_DICT, type[CollectClassNamesFromSubtreeResult]]:
    params: T_JSON_DICT = {}
    params['nodeId'] = node_id.to_json()
    cmd: T_JSON_DICT = {"method": "DOM.collectClassNamesFromSubtree", "params": params}
    return cmd, CollectClassNamesFromSubtreeResult


@dataclass
class CopyToResult:
    node_id: NodeId

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CopyToResult:
        return cls(
            node_id=NodeId.from_json(data['nodeId']),
        )


def copy_to(node_id: NodeId, target_node_id: NodeId, insert_before_node_id: Optional[NodeId] = None) -> tuple[T_JSON_DICT, type[CopyToResult]]:
    params: T_JSON_DICT = {}
    params['nodeId'] = node_id.to_json()
    params['targetNodeId'] = target_node_id.to_json()
    if insert_before_node_id is not None:
        params['insertBeforeNodeId'] = insert_before_node_id.to_json()
    cmd: T_JSON_DICT = {"method": "DOM.copyTo", "params": params}
    return cmd, CopyToResult


@dataclass
class DescribeNodeResult:
    node: Node

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DescribeNodeResult:
        return cls(
            node=Node.from_json(data['node']),
        )


def describe_node(node_id: Optional[NodeId] = None, backend_node_id: Optional[BackendNodeId] = None, object_id: Optional[RemoteObjectId] = None, depth: Optional[int] = None, pierce: Optional[bool] = None) -> tuple[T_JSON_DICT, type[DescribeNodeResult]]:
    params: T_JSON_DICT = {}
    if node_id is not None:
        params['nodeId'] = node_id.to_json()
    if backend_node_id is not None:
        params['backendNodeId'] = backend_node_id.to_json()
    if object_id is not None:
        params['objectId'] = object_id.to_json()
    if depth is not None:
        params['depth'] = depth
    if pierce is not None:
        params['pierce'] = pierce
    cmd: T_JSON_DICT = {"method": "DOM.describeNode", "params": params}
    return cmd, DescribeNodeResult


def scroll_into_view_if_needed(node_id: Optional[NodeId] = None, backend_node_id: Optional[BackendNodeId] = None, object_id: Optional[RemoteObjectId] = None, rect: Optional[Rect] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    if node_id is not None:
        params['nodeId'] = node_id.to_json()
    if backend_node_id is not None:
        params['backendNodeId'] = backend_node_id.to_json()
    if object_id is not None:
        params['objectId'] = object_id.to_json()
    if rect is not None:
        params['rect'] = rect.to_json()
    cmd: T_JSON_DICT = {"method": "DOM.scrollIntoViewIfNeeded", "params": params}
    return cmd, None


def disable() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "DOM.disable", "params": params}
    return cmd, None


def discard_search_results(search_id: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['searchId'] = search_id
    cmd: T_JSON_DICT = {"method": "DOM.discardSearchResults", "params": params}
    return cmd, None


def enable(include_whitespace: Optional[str] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    if include_whitespace is not None:
        params['includeWhitespace'] = include_whitespace
    cmd: T_JSON_DICT = {"method": "DOM.enable", "params": params}
    return cmd, None


def focus(node_id: Optional[NodeId] = None, backend_node_id: Optional[BackendNodeId] = None, object_id: Optional[RemoteObjectId] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    if node_id is not None:
        params['nodeId'] = node_id.to_json()
    if backend_node_id is not None:
        params['backendNodeId'] = backend_node_id.to_json()
    if object_id is not None:
        params['objectId'] = object_id.to_json()
    cmd: T_JSON_DICT = {"method": "DOM.focus", "params": params}
    return cmd, None


@dataclass
class GetAttributesResult:
    attributes: list[str]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetAttributesResult:
        return cls(
            attributes=[str(i) for i in data['attributes']],
        )


def get_attributes(node_id: NodeId) -> tuple[T_JSON_DICT, type[GetAttributesResult]]:
    params: T_JSON_DICT = {}
    params['nodeId'] = node_id.to_json()
    cmd: T_JSON_DICT = {"method": "DOM.getAttributes", "params": params}
    return cmd, GetAttributesResult


@dataclass
class GetBoxModelResult:
    model: BoxModel

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetBoxModelResult:
        return cls(
            model=BoxModel.from_json(data['model']),
        )


def get_box_model(node_id: Optional[NodeId] = None, backend_node_id: Optional[BackendNodeId] = None, object_id: Optional[RemoteObjectId] = None) -> tuple[T_JSON_DICT, type[GetBoxModelResult]]:
    params: T_JSON_DICT = {}
    if node_id is not None:
        params['nodeId'] = node_id.to_json()
    if backend_node_id is not None:
        params['backendNodeId'] = backend_node_id.to_json()
    if object_id is not None:
        params['objectId'] = object_id.to_json()
    cmd: T_JSON_DICT = {"method": "DOM.getBoxModel", "params": params}
    return cmd, GetBoxModelResult


@dataclass
class GetContentQuadsResult:
    quads: list[Quad]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetContentQuadsResult:
        return cls(
            quads=[Quad.from_json(i) for i in data['quads']],
        )


def get_content_quads(node_id: Optional[NodeId] = None, backend_node_id: Optional[BackendNodeId] = None, object_id: Optional[RemoteObjectId] = None) -> tuple[T_JSON_DICT, type[GetContentQuadsResult]]:
    params: T_JSON_DICT = {}
    if node_id is not None:
        params['nodeId'] = node_id.to_json()
    if backend_node_id is not None:
        params['backendNodeId'] = backend_node_id.to_json()
    if object_id is not None:
        params['objectId'] = object_id.to_json()
    cmd: T_JSON_DICT = {"method": "DOM.getContentQuads", "params": params}
    return cmd, GetContentQuadsResult


@dataclass
class GetDocumentResult:
    root: Node

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetDocumentResult:
        return cls(
            root=Node.from_json(data['root']),
        )


def get_document(depth: Optional[int] = None, pierce: Optional[bool] = None) -> tuple[T_JSON_DICT, type[GetDocumentResult]]:
    params: T_JSON_DICT = {}
    if depth is not None:
        params['depth'] = depth
    if pierce is not None:
        params['pierce'] = pierce
    cmd: T_JSON_DICT = {"method": "DOM.getDocument", "params": params}
    return cmd, GetDocumentResult


@dataclass
class GetFlattenedDocumentResult:
    nodes: list[Node]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetFlattenedDocumentResult:
        return cls(
            nodes=[Node.from_json(i) for i in data['nodes']],
        )


def get_flattened_document(depth: Optional[int] = None, pierce: Optional[bool] = None) -> tuple[T_JSON_DICT, type[GetFlattenedDocumentResult]]:
    params: T_JSON_DICT = {}
    if depth is not None:
        params['depth'] = depth
    if pierce is not None:
        params['pierce'] = pierce
    cmd: T_JSON_DICT = {"method": "DOM.getFlattenedDocument", "params": params}
    return cmd, GetFlattenedDocumentResult


@dataclass
class GetNodesForSubtreeByStyleResult:
    node_ids: list[NodeId]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetNodesForSubtreeByStyleResult:
        return cls(
            node_ids=[NodeId.from_json(i) for i in data['nodeIds']],
        )


def get_nodes_for_subtree_by_style(node_id: NodeId, computed_styles: list[CSSComputedStyleProperty], pierce: Optional[bool] = None) -> tuple[T_JSON_DICT, type[GetNodesForSubtreeByStyleResult]]:
    params: T_JSON_DICT = {}
    params['nodeId'] = node_id.to_json()
    params['computedStyles'] = [i.to_json() for i in computed_styles]
    if pierce is not None:
        params['pierce'] = pierce
    cmd: T_JSON_DICT = {"method": "DOM.getNodesForSubtreeByStyle", "params": params}
    return cmd, GetNodesForSubtreeByStyleResult


@dataclass
class GetNodeForLocationResult:
    backend_node_id: BackendNodeId
    frame_id: FrameId
    node_id: Optional[NodeId] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetNodeForLocationResult:
        return cls(
            backend_node_id=BackendNodeId.from_json(data['backendNodeId']),
            frame_id=FrameId.from_json(data['frameId']),
            node_id=NodeId.from_json(data['nodeId']) if 'nodeId' in data else None,
        )


def get_node_for_location(x: int, y: int, include_user_agent_shadow_dom: Optional[bool] = None, ignore_pointer_events_none: Optional[bool] = None) -> tuple[T_JSON_DICT, type[GetNodeForLocationResult]]:
    params: T_JSON_DICT = {}
    params['x'] = x
    params['y'] = y
    if include_user_agent_shadow_dom is not None:
        params['includeUserAgentShadowDOM'] = include_user_agent_shadow_dom
    if ignore_pointer_events_none is not None:
        params['ignorePointerEventsNone'] = ignore_pointer_events_none
    cmd: T_JSON_DICT = {"method": "DOM.getNodeForLocation", "params": params}
    return cmd, GetNodeForLocationResult


@dataclass
class GetOuterHTMLResult:
    outer_html: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetOuterHTMLResult:
        return cls(
            outer_html=str(data['outerHTML']),
        )


def get_outer_html(node_id: Optional[NodeId] = None, backend_node_id: Optional[BackendNodeId] = None, object_id: Optional[RemoteObjectId] = None, include_shadow_dom: Optional[bool] = None) -> tuple[T_JSON_DICT, type[GetOuterHTMLResult]]:
    params: T_JSON_DICT = {}
    if node_id is not None:
        params['nodeId'] = node_id.to_json()
    if backend_node_id is not None:
        params['backendNodeId'] = backend_node_id.to_json()
    if object_id is not None:
        params['objectId'] = object_id.to_json()
    if include_shadow_dom is not None:
        params['includeShadowDOM'] = include_shadow_dom
    cmd: T_JSON_DICT = {"method": "DOM.getOuterHTML", "params": params}
    return cmd, GetOuterHTMLResult


@dataclass
class GetRelayoutBoundaryResult:
    node_id: NodeId

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetRelayoutBoundaryResult:
        return cls(
            node_id=NodeId.from_json(data['nodeId']),
        )


def get_relayout_boundary(node_id: NodeId) -> tuple[T_JSON_DICT, type[GetRelayoutBoundaryResult]]:
    params: T_JSON_DICT = {}
    params['nodeId'] = node_id.to_json()
    cmd: T_JSON_DICT = {"method": "DOM.getRelayoutBoundary", "params": params}
    return cmd, GetRelayoutBoundaryResult


@dataclass
class GetSearchResultsResult:
    node_ids: list[NodeId]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetSearchResultsResult:
        return cls(
            node_ids=[NodeId.from_json(i) for i in data['nodeIds']],
        )


def get_search_results(search_id: str, from_index: int, to_index: int) -> tuple[T_JSON_DICT, type[GetSearchResultsResult]]:
    params: T_JSON_DICT = {}
    params['searchId'] = search_id
    params['fromIndex'] = from_index
    params['toIndex'] = to_index
    cmd: T_JSON_DICT = {"method": "DOM.getSearchResults", "params": params}
    return cmd, GetSearchResultsResult


def hide_highlight() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "DOM.hideHighlight", "params": params}
    return cmd, None


def highlight_node() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "DOM.highlightNode", "params": params}
    return cmd, None


def highlight_rect() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "DOM.highlightRect", "params": params}
    return cmd, None


def mark_undoable_state() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "DOM.markUndoableState", "params": params}
    return cmd, None


@dataclass
class MoveToResult:
    node_id: NodeId

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> MoveToResult:
        return cls(
            node_id=NodeId.from_json(data['nodeId']),
        )


def move_to(node_id: NodeId, target_node_id: NodeId, insert_before_node_id: Optional[NodeId] = None) -> tuple[T_JSON_DICT, type[MoveToResult]]:
    params: T_JSON_DICT = {}
    params['nodeId'] = node_id.to_json()
    params['targetNodeId'] = target_node_id.to_json()
    if insert_before_node_id is not None:
        params['insertBeforeNodeId'] = insert_before_node_id.to_json()
    cmd: T_JSON_DICT = {"method": "DOM.moveTo", "params": params}
    return cmd, MoveToResult


@dataclass
class PerformSearchResult:
    search_id: str
    result_count: int

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> PerformSearchResult:
        return cls(
            search_id=str(data['searchId']),
            result_count=int(data['resultCount']),
        )


def perform_search(query: str, include_user_agent_shadow_dom: Optional[bool] = None) -> tuple[T_JSON_DICT, type[PerformSearchResult]]:
    params: T_JSON_DICT = {}
    params['query'] = query
    if include_user_agent_shadow_dom is not None:
        params['includeUserAgentShadowDOM'] = include_user_agent_shadow_dom
    cmd: T_JSON_DICT = {"method": "DOM.performSearch", "params": params}
    return cmd, PerformSearchResult


@dataclass
class PushNodeByPathToFrontendResult:
    node_id: NodeId

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> PushNodeByPathToFrontendResult:
        return cls(
            node_id=NodeId.from_json(data['nodeId']),
        )


def push_node_by_path_to_frontend(path: str) -> tuple[T_JSON_DICT, type[PushNodeByPathToFrontendResult]]:
    params: T_JSON_DICT = {}
    params['path'] = path
    cmd: T_JSON_DICT = {"method": "DOM.pushNodeByPathToFrontend", "params": params}
    return cmd, PushNodeByPathToFrontendResult


@dataclass
class PushNodesByBackendIdsToFrontendResult:
    node_ids: list[NodeId]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> PushNodesByBackendIdsToFrontendResult:
        return cls(
            node_ids=[NodeId.from_json(i) for i in data['nodeIds']],
        )


def push_nodes_by_backend_ids_to_frontend(backend_node_ids: list[BackendNodeId]) -> tuple[T_JSON_DICT, type[PushNodesByBackendIdsToFrontendResult]]:
    params: T_JSON_DICT = {}
    params['backendNodeIds'] = [i.to_json() for i in backend_node_ids]
    cmd: T_JSON_DICT = {"method": "DOM.pushNodesByBackendIdsToFrontend", "params": params}
    return cmd, PushNodesByBackendIdsToFrontendResult


@dataclass
class QuerySelectorResult:
    node_id: NodeId

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> QuerySelectorResult:
        return cls(
            node_id=NodeId.from_json(data['nodeId']),
        )


def query_selector(node_id: NodeId, selector: str) -> tuple[T_JSON_DICT, type[QuerySelectorResult]]:
    params: T_JSON_DICT = {}
    params['nodeId'] = node_id.to_json()
    params['selector'] = selector
    cmd: T_JSON_DICT = {"method": "DOM.querySelector", "params": params}
    return cmd, QuerySelectorResult


@dataclass
class QuerySelectorAllResult:
    node_ids: list[NodeId]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> QuerySelectorAllResult:
        return cls(
            node_ids=[NodeId.from_json(i) for i in data['nodeIds']],
        )


def query_selector_all(node_id: NodeId, selector: str) -> tuple[T_JSON_DICT, type[QuerySelectorAllResult]]:
    params: T_JSON_DICT = {}
    params['nodeId'] = node_id.to_json()
    params['selector'] = selector
    cmd: T_JSON_DICT = {"method": "DOM.querySelectorAll", "params": params}
    return cmd, QuerySelectorAllResult


@dataclass
class GetTopLayerElementsResult:
    node_ids: list[NodeId]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetTopLayerElementsResult:
        return cls(
            node_ids=[NodeId.from_json(i) for i in data['nodeIds']],
        )


def get_top_layer_elements() -> tuple[T_JSON_DICT, type[GetTopLayerElementsResult]]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "DOM.getTopLayerElements", "params": params}
    return cmd, GetTopLayerElementsResult


@dataclass
class GetElementByRelationResult:
    node_id: NodeId

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetElementByRelationResult:
        return cls(
            node_id=NodeId.from_json(data['nodeId']),
        )


def get_element_by_relation(node_id: NodeId, relation: str) -> tuple[T_JSON_DICT, type[GetElementByRelationResult]]:
    params: T_JSON_DICT = {}
    params['nodeId'] = node_id.to_json()
    params['relation'] = relation
    cmd: T_JSON_DICT = {"method": "DOM.getElementByRelation", "params": params}
    return cmd, GetElementByRelationResult


def redo() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "DOM.redo", "params": params}
    return cmd, None


def remove_attribute(node_id: NodeId, name: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['nodeId'] = node_id.to_json()
    params['name'] = name
    cmd: T_JSON_DICT = {"method": "DOM.removeAttribute", "params": params}
    return cmd, None


def remove_node(node_id: NodeId) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['nodeId'] = node_id.to_json()
    cmd: T_JSON_DICT = {"method": "DOM.removeNode", "params": params}
    return cmd, None


def request_child_nodes(node_id: NodeId, depth: Optional[int] = None, pierce: Optional[bool] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['nodeId'] = node_id.to_json()
    if depth is not None:
        params['depth'] = depth
    if pierce is not None:
        params['pierce'] = pierce
    cmd: T_JSON_DICT = {"method": "DOM.requestChildNodes", "params": params}
    return cmd, None


@dataclass
class RequestNodeResult:
    node_id: NodeId

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> RequestNodeResult:
        return cls(
            node_id=NodeId.from_json(data['nodeId']),
        )


def request_node(object_id: RemoteObjectId) -> tuple[T_JSON_DICT, type[RequestNodeResult]]:
    params: T_JSON_DICT = {}
    params['objectId'] = object_id.to_json()
    cmd: T_JSON_DICT = {"method": "DOM.requestNode", "params": params}
    return cmd, RequestNodeResult


@dataclass
class ResolveNodeResult:
    object: RemoteObject

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ResolveNodeResult:
        return cls(
            object=RemoteObject.from_json(data['object']),
        )


def resolve_node(node_id: Optional[NodeId] = None, backend_node_id: Optional[BackendNodeId] = None, object_group: Optional[str] = None, execution_context_id: Optional[ExecutionContextId] = None) -> tuple[T_JSON_DICT, type[ResolveNodeResult]]:
    params: T_JSON_DICT = {}
    if node_id is not None:
        params['nodeId'] = node_id.to_json()
    if backend_node_id is not None:
        params['backendNodeId'] = backend_node_id.to_json()
    if object_group is not None:
        params['objectGroup'] = object_group
    if execution_context_id is not None:
        params['executionContextId'] = execution_context_id.to_json()
    cmd: T_JSON_DICT = {"method": "DOM.resolveNode", "params": params}
    return cmd, ResolveNodeResult


def set_attribute_value(node_id: NodeId, name: str, value: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['nodeId'] = node_id.to_json()
    params['name'] = name
    params['value'] = value
    cmd: T_JSON_DICT = {"method": "DOM.setAttributeValue", "params": params}
    return cmd, None


def set_attributes_as_text(node_id: NodeId, text: str, name: Optional[str] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['nodeId'] = node_id.to_json()
    params['text'] = text
    if name is not None:
        params['name'] = name
    cmd: T_JSON_DICT = {"method": "DOM.setAttributesAsText", "params": params}
    return cmd, None


def set_file_input_files(files: list[str], node_id: Optional[NodeId] = None, backend_node_id: Optional[BackendNodeId] = None, object_id: Optional[RemoteObjectId] = None) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['files'] = list(files)
    if node_id is not None:
        params['nodeId'] = node_id.to_json()
    if backend_node_id is not None:
        params['backendNodeId'] = backend_node_id.to_json()
    if object_id is not None:
        params['objectId'] = object_id.to_json()
    cmd: T_JSON_DICT = {"method": "DOM.setFileInputFiles", "params": params}
    return cmd, None


def set_node_stack_traces_enabled(enable: bool) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['enable'] = enable
    cmd: T_JSON_DICT = {"method": "DOM.setNodeStackTracesEnabled", "params": params}
    return cmd, None


@dataclass
class GetNodeStackTracesResult:
    creation: Optional[StackTrace] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetNodeStackTracesResult:
        return cls(
            creation=StackTrace.from_json(data['creation']) if 'creation' in data else None,
        )


def get_node_stack_traces(node_id: NodeId) -> tuple[T_JSON_DICT, type[GetNodeStackTracesResult]]:
    params: T_JSON_DICT = {}
    params['nodeId'] = node_id.to_json()
    cmd: T_JSON_DICT = {"method": "DOM.getNodeStackTraces", "params": params}
    return cmd, GetNodeStackTracesResult


@dataclass
class GetFileInfoResult:
    path: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetFileInfoResult:
        return cls(
            path=str(data['path']),
        )


def get_file_info(object_id: RemoteObjectId) -> tuple[T_JSON_DICT, type[GetFileInfoResult]]:
    params: T_JSON_DICT = {}
    params['objectId'] = object_id.to_json()
    cmd: T_JSON_DICT = {"method": "DOM.getFileInfo", "params": params}
    return cmd, GetFileInfoResult


@dataclass
class GetDetachedDomNodesResult:
    detached_nodes: list[DetachedElementInfo]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetDetachedDomNodesResult:
        return cls(
            detached_nodes=[DetachedElementInfo.from_json(i) for i in data['detachedNodes']],
        )


def get_detached_dom_nodes() -> tuple[T_JSON_DICT, type[GetDetachedDomNodesResult]]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "DOM.getDetachedDomNodes", "params": params}
    return cmd, GetDetachedDomNodesResult


def set_inspected_node(node_id: NodeId) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['nodeId'] = node_id.to_json()
    cmd: T_JSON_DICT = {"method": "DOM.setInspectedNode", "params": params}
    return cmd, None


@dataclass
class SetNodeNameResult:
    node_id: NodeId

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SetNodeNameResult:
        return cls(
            node_id=NodeId.from_json(data['nodeId']),
        )


def set_node_name(node_id: NodeId, name: str) -> tuple[T_JSON_DICT, type[SetNodeNameResult]]:
    params: T_JSON_DICT = {}
    params['nodeId'] = node_id.to_json()
    params['name'] = name
    cmd: T_JSON_DICT = {"method": "DOM.setNodeName", "params": params}
    return cmd, SetNodeNameResult


def set_node_value(node_id: NodeId, value: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['nodeId'] = node_id.to_json()
    params['value'] = value
    cmd: T_JSON_DICT = {"method": "DOM.setNodeValue", "params": params}
    return cmd, None


def set_outer_html(node_id: NodeId, outer_html: str) -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    params['nodeId'] = node_id.to_json()
    params['outerHTML'] = outer_html
    cmd: T_JSON_DICT = {"method": "DOM.setOuterHTML", "params": params}
    return cmd, None


def undo() -> tuple[T_JSON_DICT, None]:
    params: T_JSON_DICT = {}
    cmd: T_JSON_DICT = {"method": "DOM.undo", "params": params}
    return cmd, None


@dataclass
class GetFrameOwnerResult:
    backend_node_id: BackendNodeId
    node_id: Optional[NodeId] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetFrameOwnerResult:
        return cls(
            backend_node_id=BackendNodeId.from_json(data['backendNodeId']),
            node_id=NodeId.from_json(data['nodeId']) if 'nodeId' in data else None,
        )


def get_frame_owner(frame_id: FrameId) -> tuple[T_JSON_DICT, type[GetFrameOwnerResult]]:
    params: T_JSON_DICT = {}
    params['frameId'] = frame_id.to_json()
    cmd: T_JSON_DICT = {"method": "DOM.getFrameOwner", "params": params}
    return cmd, GetFrameOwnerResult


@dataclass
class GetContainerForNodeResult:
    node_id: Optional[NodeId] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetContainerForNodeResult:
        return cls(
            node_id=NodeId.from_json(data['nodeId']) if 'nodeId' in data else None,
        )


def get_container_for_node(node_id: NodeId, container_name: Optional[str] = None, physical_axes: Optional[PhysicalAxes] = None, logical_axes: Optional[LogicalAxes] = None, queries_scroll_state: Optional[bool] = None, queries_anchored: Optional[bool] = None) -> tuple[T_JSON_DICT, type[GetContainerForNodeResult]]:
    params: T_JSON_DICT = {}
    params['nodeId'] = node_id.to_json()
    if container_name is not None:
        params['containerName'] = container_name
    if physical_axes is not None:
        params['physicalAxes'] = physical_axes.to_json()
    if logical_axes is not None:
        params['logicalAxes'] = logical_axes.to_json()
    if queries_scroll_state is not None:
        params['queriesScrollState'] = queries_scroll_state
    if queries_anchored is not None:
        params['queriesAnchored'] = queries_anchored
    cmd: T_JSON_DICT = {"method": "DOM.getContainerForNode", "params": params}
    return cmd, GetContainerForNodeResult


@dataclass
class GetQueryingDescendantsForContainerResult:
    node_ids: list[NodeId]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetQueryingDescendantsForContainerResult:
        return cls(
            node_ids=[NodeId.from_json(i) for i in data['nodeIds']],
        )


def get_querying_descendants_for_container(node_id: NodeId) -> tuple[T_JSON_DICT, type[GetQueryingDescendantsForContainerResult]]:
    params: T_JSON_DICT = {}
    params['nodeId'] = node_id.to_json()
    cmd: T_JSON_DICT = {"method": "DOM.getQueryingDescendantsForContainer", "params": params}
    return cmd, GetQueryingDescendantsForContainerResult


@dataclass
class GetAnchorElementResult:
    node_id: NodeId

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> GetAnchorElementResult:
        return cls(
            node_id=NodeId.from_json(data['nodeId']),
        )


def get_anchor_element(node_id: NodeId, anchor_specifier: Optional[str] = None) -> tuple[T_JSON_DICT, type[GetAnchorElementResult]]:
    params: T_JSON_DICT = {}
    params['nodeId'] = node_id.to_json()
    if anchor_specifier is not None:
        params['anchorSpecifier'] = anchor_specifier
    cmd: T_JSON_DICT = {"method": "DOM.getAnchorElement", "params": params}
    return cmd, GetAnchorElementResult


@dataclass
class ForceShowPopoverResult:
    node_ids: list[NodeId]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ForceShowPopoverResult:
        return cls(
            node_ids=[NodeId.from_json(i) for i in data['nodeIds']],
        )


def force_show_popover(node_id: NodeId, enable: bool) -> tuple[T_JSON_DICT, type[ForceShowPopoverResult]]:
    params: T_JSON_DICT = {}
    params['nodeId'] = node_id.to_json()
    params['enable'] = enable
    cmd: T_JSON_DICT = {"method": "DOM.forceShowPopover", "params": params}
    return cmd, ForceShowPopoverResult


@dataclass
class AttributeModified:
    EVENT_NAME: str = field(init=False, repr=False, default="DOM.attributeModified")
    node_id: NodeId
    name: str
    value: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> AttributeModified:
        return cls(
            node_id=NodeId.from_json(data['nodeId']),
            name=str(data['name']),
            value=str(data['value']),
        )


@dataclass
class AdoptedStyleSheetsModified:
    EVENT_NAME: str = field(init=False, repr=False, default="DOM.adoptedStyleSheetsModified")
    node_id: NodeId
    adopted_style_sheets: list[StyleSheetId]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> AdoptedStyleSheetsModified:
        return cls(
            node_id=NodeId.from_json(data['nodeId']),
            adopted_style_sheets=[StyleSheetId.from_json(i) for i in data['adoptedStyleSheets']],
        )


@dataclass
class AttributeRemoved:
    EVENT_NAME: str = field(init=False, repr=False, default="DOM.attributeRemoved")
    node_id: NodeId
    name: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> AttributeRemoved:
        return cls(
            node_id=NodeId.from_json(data['nodeId']),
            name=str(data['name']),
        )


@dataclass
class CharacterDataModified:
    EVENT_NAME: str = field(init=False, repr=False, default="DOM.characterDataModified")
    node_id: NodeId
    character_data: str

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> CharacterDataModified:
        return cls(
            node_id=NodeId.from_json(data['nodeId']),
            character_data=str(data['characterData']),
        )


@dataclass
class ChildNodeCountUpdated:
    EVENT_NAME: str = field(init=False, repr=False, default="DOM.childNodeCountUpdated")
    node_id: NodeId
    child_node_count: int

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ChildNodeCountUpdated:
        return cls(
            node_id=NodeId.from_json(data['nodeId']),
            child_node_count=int(data['childNodeCount']),
        )


@dataclass
class ChildNodeInserted:
    EVENT_NAME: str = field(init=False, repr=False, default="DOM.childNodeInserted")
    parent_node_id: NodeId
    previous_node_id: NodeId
    node: Node

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ChildNodeInserted:
        return cls(
            parent_node_id=NodeId.from_json(data['parentNodeId']),
            previous_node_id=NodeId.from_json(data['previousNodeId']),
            node=Node.from_json(data['node']),
        )


@dataclass
class ChildNodeRemoved:
    EVENT_NAME: str = field(init=False, repr=False, default="DOM.childNodeRemoved")
    parent_node_id: NodeId
    node_id: NodeId

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ChildNodeRemoved:
        return cls(
            parent_node_id=NodeId.from_json(data['parentNodeId']),
            node_id=NodeId.from_json(data['nodeId']),
        )


@dataclass
class DistributedNodesUpdated:
    EVENT_NAME: str = field(init=False, repr=False, default="DOM.distributedNodesUpdated")
    insertion_point_id: NodeId
    distributed_nodes: list[BackendNode]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DistributedNodesUpdated:
        return cls(
            insertion_point_id=NodeId.from_json(data['insertionPointId']),
            distributed_nodes=[BackendNode.from_json(i) for i in data['distributedNodes']],
        )


@dataclass
class DocumentUpdated:
    EVENT_NAME: str = field(init=False, repr=False, default="DOM.documentUpdated")

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> DocumentUpdated:
        return cls()


@dataclass
class InlineStyleInvalidated:
    EVENT_NAME: str = field(init=False, repr=False, default="DOM.inlineStyleInvalidated")
    node_ids: list[NodeId]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> InlineStyleInvalidated:
        return cls(
            node_ids=[NodeId.from_json(i) for i in data['nodeIds']],
        )


@dataclass
class PseudoElementAdded:
    EVENT_NAME: str = field(init=False, repr=False, default="DOM.pseudoElementAdded")
    parent_id: NodeId
    pseudo_element: Node

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> PseudoElementAdded:
        return cls(
            parent_id=NodeId.from_json(data['parentId']),
            pseudo_element=Node.from_json(data['pseudoElement']),
        )


@dataclass
class TopLayerElementsUpdated:
    EVENT_NAME: str = field(init=False, repr=False, default="DOM.topLayerElementsUpdated")

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> TopLayerElementsUpdated:
        return cls()


@dataclass
class ScrollableFlagUpdated:
    EVENT_NAME: str = field(init=False, repr=False, default="DOM.scrollableFlagUpdated")
    node_id: NodeId
    is_scrollable: bool

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ScrollableFlagUpdated:
        return cls(
            node_id=NodeId.from_json(data['nodeId']),
            is_scrollable=bool(data['isScrollable']),
        )


@dataclass
class AdRelatedStateUpdated:
    EVENT_NAME: str = field(init=False, repr=False, default="DOM.adRelatedStateUpdated")
    node_id: NodeId
    ad_provenance: Optional[AdProvenance] = None

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> AdRelatedStateUpdated:
        return cls(
            node_id=NodeId.from_json(data['nodeId']),
            ad_provenance=AdProvenance.from_json(data['adProvenance']) if 'adProvenance' in data else None,
        )


@dataclass
class AffectedByStartingStylesFlagUpdated:
    EVENT_NAME: str = field(init=False, repr=False, default="DOM.affectedByStartingStylesFlagUpdated")
    node_id: NodeId
    affected_by_starting_styles: bool

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> AffectedByStartingStylesFlagUpdated:
        return cls(
            node_id=NodeId.from_json(data['nodeId']),
            affected_by_starting_styles=bool(data['affectedByStartingStyles']),
        )


@dataclass
class PseudoElementRemoved:
    EVENT_NAME: str = field(init=False, repr=False, default="DOM.pseudoElementRemoved")
    parent_id: NodeId
    pseudo_element_id: NodeId

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> PseudoElementRemoved:
        return cls(
            parent_id=NodeId.from_json(data['parentId']),
            pseudo_element_id=NodeId.from_json(data['pseudoElementId']),
        )


@dataclass
class SetChildNodes:
    EVENT_NAME: str = field(init=False, repr=False, default="DOM.setChildNodes")
    parent_id: NodeId
    nodes: list[Node]

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> SetChildNodes:
        return cls(
            parent_id=NodeId.from_json(data['parentId']),
            nodes=[Node.from_json(i) for i in data['nodes']],
        )


@dataclass
class ShadowRootPopped:
    EVENT_NAME: str = field(init=False, repr=False, default="DOM.shadowRootPopped")
    host_id: NodeId
    root_id: NodeId

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ShadowRootPopped:
        return cls(
            host_id=NodeId.from_json(data['hostId']),
            root_id=NodeId.from_json(data['rootId']),
        )


@dataclass
class ShadowRootPushed:
    EVENT_NAME: str = field(init=False, repr=False, default="DOM.shadowRootPushed")
    host_id: NodeId
    root: Node

    @classmethod
    def from_json(cls, data: T_JSON_DICT) -> ShadowRootPushed:
        return cls(
            host_id=NodeId.from_json(data['hostId']),
            root=Node.from_json(data['root']),
        )

