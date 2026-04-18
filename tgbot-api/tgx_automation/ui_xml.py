from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass


@dataclass
class UiNode:
    text: str
    resource_id: str
    content_desc: str
    clickable: bool
    bounds: str

    @property
    def center(self) -> tuple[int, int] | None:
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", self.bounds)
        if not m:
            return None
        x1, y1, x2, y2 = map(int, m.groups())
        return ((x1 + x2) // 2, (y1 + y2) // 2)


def parse_nodes(xml: str) -> list[UiNode]:
    nodes: list[UiNode] = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return nodes

    for node in root.iter("node"):
        nodes.append(
            UiNode(
                text=node.attrib.get("text", ""),
                resource_id=node.attrib.get("resource-id", ""),
                content_desc=node.attrib.get("content-desc", ""),
                clickable=node.attrib.get("clickable", "false") == "true",
                bounds=node.attrib.get("bounds", ""),
            )
        )
    return nodes


def find_node_by_text(xml: str, candidates: list[str]) -> UiNode | None:
    cands = [c.lower() for c in candidates]
    for node in parse_nodes(xml):
        t = node.text.lower()
        if t and any(c in t for c in cands):
            return node
    return None


def find_node_by_resource(xml: str, resource_contains: list[str]) -> UiNode | None:
    cands = [c.lower() for c in resource_contains]
    for node in parse_nodes(xml):
        rid = node.resource_id.lower()
        if rid and any(c in rid for c in cands):
            return node
    return None


def find_top_right_close(xml: str) -> UiNode | None:
    for node in parse_nodes(xml):
        c = node.center
        if not c:
            continue
        x, y = c
        if node.clickable and x >= 560 and 40 <= y <= 360:
            return node
    return None
