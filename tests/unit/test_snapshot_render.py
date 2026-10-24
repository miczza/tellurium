"""Pruning and rendering of the accessibility snapshot, on AX trees recorded from
the fixture pages (``tests/fixtures/ax``, see ``record_ax_trees.py``)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from tellurium.browser.refs import RefMap
from tellurium.browser.snapshot import AXTree, SnapshotNode, build_nodes, render

AX = Path(__file__).parents[1] / "fixtures" / "ax"


def _tree(name: str) -> AXTree:
    return AXTree.from_json(json.loads((AX / f"{name}.json").read_text()))


def _snapshot(tree: AXTree, refs: RefMap | None = None, **kw) -> str:
    max_chars = kw.pop("max_chars", None)
    refs = refs or RefMap()
    return render(build_nodes(tree, refs.ref_for, **kw), max_chars=max_chars)


FORM = """\
- navigation [ref=e1]:
  - link "Home" [ref=e2]
  - link "Help" [ref=e3]
- main [ref=e4]:
  - heading "Sign in" [level=1] [ref=e5]
  - text: Welcome back, please sign in.
  - form [ref=e6]:
    - text: Email
    - textbox "Email" [ref=e7]: ada@example.com
    - text: Password
    - textbox "Password" [ref=e8]
    - checkbox "Remember me" [checked] [ref=e9]
    - text: Language
    - combobox "Language" [expanded=false] [ref=e10]: Italiano
      - option "English" [ref=e11]
      - option "Italiano" [selected] [ref=e12]
    - button "Sign in" [ref=e13]
    - button "Single sign-on" [disabled] [ref=e14]
    - button "More options" [expanded=false] [ref=e15]
  - heading "Need help?" [level=2] [ref=e16]
  - paragraph [ref=e17]:
    - text: Write to
    - link "support" [ref=e18]
    - text: any time."""

FORM_INTERACTIVE = """\
- link "Home" [ref=e1]
- link "Help" [ref=e2]
- textbox "Email" [ref=e3]: ada@example.com
- textbox "Password" [ref=e4]
- checkbox "Remember me" [checked] [ref=e5]
- combobox "Language" [expanded=false] [ref=e6]: Italiano
  - option "English" [ref=e7]
  - option "Italiano" [selected] [ref=e8]
- button "Sign in" [ref=e9]
- button "Single sign-on" [disabled] [ref=e10]
- button "More options" [expanded=false] [ref=e11]
- link "support" [ref=e12]"""


def test_form_renders_compact_tree():
    assert _snapshot(_tree("form")) == FORM


def test_interactive_keeps_only_usable_nodes():
    assert _snapshot(_tree("form"), interactive=True) == FORM_INTERACTIVE


def test_structured_nodes_carry_value_and_states():
    nodes = build_nodes(_tree("form"), RefMap().ref_for, interactive=True)
    email, password, remember, language = nodes[2:6]
    assert email == SnapshotNode(ref="e3", role="textbox", name="Email", value="ada@example.com")
    assert password.value is None
    assert remember.states == {"checked": True}
    assert language.value == "Italiano"
    assert language.states == {"expanded": False}
    assert [o.name for o in language.children] == ["English", "Italiano"]
    assert language.children[1].states == {"selected": True}


def test_same_node_keeps_its_ref_across_snapshots_and_modes():
    refs = RefMap()
    tree = _tree("form")
    first = _snapshot(tree, refs, interactive=True)
    full = _snapshot(tree, refs)
    assert 'textbox "Email" [ref=e3]' in first
    assert 'textbox "Email" [ref=e3]' in full
    assert _snapshot(tree, refs) == full
    # the ref leads back to the <input id="email"> backend node
    assert refs.lookup("e3") == 2


def test_depth_limits_levels():
    assert _snapshot(_tree("form"), depth=1) == "- navigation [ref=e1]\n- main [ref=e2]"
    two = _snapshot(_tree("form"), depth=2)
    assert '  - heading "Sign in" [level=1]' in two
    assert "  - form [ref=" in two
    assert "textbox" not in two
    # text is a level too: nothing leaks from below the cut
    assert "Email" not in two


def test_depth_zero_is_empty():
    assert _snapshot(_tree("form"), depth=0) == ""


def test_negative_depth_is_rejected():
    with pytest.raises(ValueError):
        build_nodes(_tree("form"), RefMap().ref_for, depth=-1)


def test_root_scopes_to_a_subtree():
    # backend node 1 is <form id="login"> in the recording
    text = _snapshot(_tree("form"), root=1)
    assert text.startswith("- form [ref=e1]:\n  - text: Email\n")
    assert "navigation" not in text
    assert "Need help?" not in text


def test_root_not_in_tree_gives_nothing():
    assert build_nodes(_tree("form"), RefMap().ref_for, root=987654) == []


def test_max_chars_cuts_with_an_explicit_signal():
    full = _snapshot(_tree("form"))
    cut = _snapshot(_tree("form"), max_chars=300)
    assert len(cut) <= 300
    assert cut != full
    last = cut.splitlines()[-1]
    assert "truncated" in last
    hidden = len(full.splitlines()) - (len(cut.splitlines()) - 1)
    assert f"{hidden} more lines" in last
    # whole lines only
    assert full.startswith("\n".join(cut.splitlines()[:-1]))


def test_max_chars_large_enough_changes_nothing():
    full = _snapshot(_tree("form"))
    assert _snapshot(_tree("form"), max_chars=len(full)) == full


def test_max_chars_must_be_positive():
    with pytest.raises(ValueError):
        render([], max_chars=0)


def test_same_process_iframe_is_stitched_under_its_node():
    assert _snapshot(_tree("iframe")) == (
        '- heading "Parent" [level=1] [ref=e1]\n'
        '- button "Top button" [ref=e2]\n'
        '- iframe "Child frame" [ref=e3]:\n'
        "  - paragraph [ref=e4]: Inside the frame\n"
        '  - button "Inner button" [ref=e5]'
    )


def test_interactive_reaches_into_same_process_iframes():
    assert _snapshot(_tree("iframe"), interactive=True) == (
        '- button "Top button" [ref=e1]\n- button "Inner button" [ref=e2]'
    )


def test_oopif_is_a_placeholder_line():
    assert _snapshot(_tree("oopif")) == (
        '- heading "Host" [level=1] [ref=e1]\n'
        '- iframe "http://b.test:8000/snapshot_child.html" [oopif]'
    )
    nodes = build_nodes(_tree("oopif"), RefMap().ref_for)
    assert nodes[1] == SnapshotNode(
        ref=None,
        role="iframe",
        name="http://b.test:8000/snapshot_child.html",
        states={"oopif": True},
    )


# ----------------------------------------------------------------------------
# Hand-made trees for the edge cases


def _node(nid, role, name="", children=(), *, ignored=False, value=None, props=None, backend=None):
    node = {
        "nodeId": str(nid),
        "ignored": ignored,
        "role": {"value": role},
        "name": {"value": name},
        "childIds": [str(c) for c in children],
        "backendDOMNodeId": nid if backend is None else backend,
    }
    if value is not None:
        node["value"] = {"value": value}
    if props:
        node["properties"] = [{"name": k, "value": {"value": v}} for k, v in props.items()]
    return node


def test_ignored_subtrees_and_list_markers_vanish():
    tree = AXTree(
        nodes=[
            _node(1, "RootWebArea", "Doc", [2, 5]),
            _node(2, "list", "", [3]),
            _node(3, "listitem", "", [4, 6]),
            _node(4, "ListMarker", "• ", [7]),
            _node(7, "StaticText", "• "),
            _node(6, "StaticText", "  first\n item "),
            _node(5, "generic", "", [8], ignored=True),
            _node(8, "StaticText", "hidden", ignored=True),
        ]
    )
    assert _snapshot(tree) == "- list [ref=e1]:\n  - listitem [ref=e2]: first item"


def test_text_equal_to_the_name_is_not_repeated():
    tree = AXTree(
        nodes=[
            _node(1, "RootWebArea", "Doc", [2]),
            _node(2, "link", "Read  more", [3, 4]),
            _node(3, "StaticText", "Read "),
            _node(4, "StaticText", " more"),
        ]
    )
    assert _snapshot(tree) == '- link "Read more" [ref=e1]'


def test_names_are_quoted_safely():
    tree = AXTree(nodes=[_node(1, "RootWebArea", "", [2]), _node(2, "button", 'Say "hi"\n')])
    assert _snapshot(tree) == '- button "Say \\"hi\\"" [ref=e1]'


def test_contenteditable_counts_as_interactive():
    tree = AXTree(
        nodes=[
            _node(1, "RootWebArea", "", [2]),
            _node(2, "generic", "Notes", props={"editable": "richtext", "focusable": True}),
        ]
    )
    assert _snapshot(tree, interactive=True) == '- generic "Notes" [ref=e1]'


def test_pathologically_deep_tree_does_not_crash():
    depth = 3000
    nodes = [_node(1, "RootWebArea", "", [2])]
    for i in range(2, depth):
        nodes.append(_node(i, "generic", "", [i + 1]))
    nodes.append(_node(depth, "button", "Deep"))
    text = _snapshot(AXTree(nodes=nodes))
    assert "RecursionError" not in text  # it returned at all


def _big_tree(items: int) -> AXTree:
    """A list page shaped like Chrome's: li > (ListMarker, StaticText, button > text)."""
    nodes = [_node(1, "RootWebArea", "Big", [2]), _node(2, "list", "", [])]
    nid = 3
    for i in range(items):
        li, marker, text, button, label = range(nid, nid + 5)
        nid += 5
        nodes[1]["childIds"].append(str(li))
        nodes += [
            _node(li, "listitem", "", [marker, text, button], props={"level": 1}),
            _node(marker, "ListMarker", "• "),
            _node(text, "StaticText", f"Item {i}"),
            _node(button, "button", f"Open {i}", [label], props={"focusable": True}),
            _node(label, "StaticText", f"Open {i}"),
        ]
    return AXTree(nodes=nodes)


def test_five_thousand_nodes_build_and_render_fast():
    tree = _big_tree(1000)  # 5002 AX nodes
    start = time.perf_counter()
    text = _snapshot(tree)
    elapsed = time.perf_counter() - start
    assert text.count("\n") + 1 == 1 + 1000 * 3
    assert elapsed < 0.15, f"pure build+render took {elapsed * 1000:.0f} ms"
