"""
xmind_writer.py
将血缘树（dict 格式）导出为标准 .xmind 文件。

.xmind 文件本质是一个 zip 压缩包，包含：
  - content.xml   —— 主题树结构
  - META-INF/container.xml
  - manifest.json（XMind 8+）或 meta.xml

本模块兼容 XMind 8 / XMind 2020 / XMind 2023 格式（content.xml 方案）。
"""
from __future__ import annotations

import io
import json
import uuid
import zipfile
from datetime import datetime
from typing import Dict, Any, List


# ─────────────────────────────────────────────────────────────
# 内部 XML 生成器
# ─────────────────────────────────────────────────────────────

def _gen_id() -> str:
    return uuid.uuid4().hex[:16]


def _obj_type_emoji(obj_type: str) -> str:
    """给不同对象类型加前缀标注，方便在 XMind 中一眼区分"""
    mapping = {
        "TABLE": "[表]",
        "VIEW": "[视图]",
        "PROCEDURE": "[SP]",
        "FUNCTION": "[函数]",
        "UNKNOWN": "[未知]",
    }
    return mapping.get(obj_type.upper(), f"[{obj_type}]")


def _build_topic_xml(node: Dict[str, Any], indent: int = 0) -> str:
    """
    递归生成 XMind content.xml 的 <topic> 片段。
    node 结构：{"name": ..., "obj_type": ..., "children": [...], "_cycle": bool}
    """
    pad = "  " * indent
    topic_id = _gen_id()
    label = _obj_type_emoji(node.get("obj_type", "UNKNOWN")) + " " + node["name"]
    if node.get("_cycle"):
        label += "  ↩循环引用"

    source = node.get("source_file", "")
    note_xml = ""
    if source:
        # 把来源文件路径写到备注里
        escaped = source.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        note_xml = f"""{pad}    <notes><plain><content>{escaped}</content></plain></notes>"""

    children = node.get("children", [])
    if children:
        children_xml = f"{pad}    <children>\n"
        children_xml += f"{pad}      <topics type=\"attached\">\n"
        for child in children:
            children_xml += _build_topic_xml(child, indent + 4)
        children_xml += f"{pad}      </topics>\n"
        children_xml += f"{pad}    </children>\n"
    else:
        children_xml = ""

    return (
        f"{pad}  <topic id=\"{topic_id}\">\n"
        f"{pad}    <title>{_xml_escape(label)}</title>\n"
        f"{note_xml}\n"
        f"{children_xml}"
        f"{pad}  </topic>\n"
    )


def _xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace("\"", "&quot;"))


def _build_content_xml(
    root_node: Dict[str, Any],
    sheet_title: str = "血缘分析",
    direction: str = "下游（谁引用了我）",
) -> str:
    """生成完整的 content.xml 字符串"""
    timestamp = int(datetime.now().timestamp() * 1000)
    sheet_id = _gen_id()
    root_id = _gen_id()

    root_label = (
        f"{_obj_type_emoji(root_node.get('obj_type', 'UNKNOWN'))} "
        f"{root_node['name']}  [{direction}]"
    )

    children = root_node.get("children", [])
    if children:
        children_xml = "    <children>\n      <topics type=\"attached\">\n"
        for child in children:
            children_xml += _build_topic_xml(child, indent=2)
        children_xml += "      </topics>\n    </children>\n"
    else:
        children_xml = ""

    return f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<xmap-content xmlns="urn:xmind:xmap:xmlns:content:2.0"
              xmlns:fo="http://www.w3.org/1999/XSL/Format"
              xmlns:svg="http://www.w3.org/2000/svg"
              xmlns:xhtml="http://www.w3.org/1999/xhtml"
              xmlns:xlink="http://www.w3.org/1999/xlink"
              version="2.0">
  <sheet id="{sheet_id}" timestamp="{timestamp}">
    <topic id="{root_id}" timestamp="{timestamp}">
      <title>{_xml_escape(root_label)}</title>
{children_xml}    </topic>
    <title>{_xml_escape(sheet_title)}</title>
  </sheet>
</xmap-content>
"""


_MANIFEST_JSON = json.dumps({
    "file-entries": {
        "content.xml": {},
        "META-INF/": {},
    }
}, indent=2)

_META_XML = """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<meta xmlns="urn:xmind:xmap:xmlns:meta:2.0" version="2.0"/>
"""

_CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles>
    <rootfile full-path="content.xml" media-type="application/xmind+xml"/>
  </rootfiles>
</container>
"""


# ─────────────────────────────────────────────────────────────
# 公开接口
# ─────────────────────────────────────────────────────────────

def export_to_bytes(
    tree: Dict[str, Any],
    sheet_title: str = "血缘分析",
    direction: str = "下游（谁引用了我）",
) -> bytes:
    """
    将血缘树转换为 .xmind 文件的二进制内容（用于 HTTP 下载或写文件）。

    :param tree:         血缘树 dict（来自 LineageGraph.get_dependents_tree）
    :param sheet_title:  XMind Sheet 标题
    :param direction:    说明是上游/下游分析，写入根节点标题
    :return:             .xmind 文件的 bytes
    """
    content_xml = _build_content_xml(tree, sheet_title, direction)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content.xml", content_xml.encode("utf-8"))
        zf.writestr("meta.xml", _META_XML)
        zf.writestr("META-INF/container.xml", _CONTAINER_XML)
        zf.writestr("manifest.json", _MANIFEST_JSON)

    return buf.getvalue()


def export_to_file(
    tree: Dict[str, Any],
    output_path: str,
    sheet_title: str = "血缘分析",
    direction: str = "下游（谁引用了我）",
) -> None:
    """
    将血缘树写入指定 .xmind 文件路径。

    :param tree:         血缘树 dict
    :param output_path:  输出文件路径，例如 "output/A_lineage.xmind"
    :param sheet_title:  XMind Sheet 标题
    :param direction:    分析方向说明
    """
    data = export_to_bytes(tree, sheet_title, direction)
    with open(output_path, "wb") as f:
        f.write(data)
    print(f"XMind 文件已导出: {output_path}")


def export_both_directions(
    dependents_tree: Dict[str, Any],
    dependencies_tree: Dict[str, Any],
    output_path: str,
    obj_name: str,
) -> None:
    """
    将上下游两棵树导出到同一个 .xmind 文件的两个 Sheet 中。

    :param dependents_tree:   下游树（谁引用了我）
    :param dependencies_tree: 上游树（我引用了谁）
    :param output_path:       输出路径
    :param obj_name:          搜索的对象名
    """
    down_xml = _build_content_xml(
        dependents_tree,
        sheet_title=f"{obj_name} — 下游（谁引用了我）",
        direction="下游（谁引用了我）",
    )
    up_xml = _build_content_xml(
        dependencies_tree,
        sheet_title=f"{obj_name} — 上游（我依赖了谁）",
        direction="上游（我依赖了谁）",
    )

    # 合并两个 sheet 到一个 content.xml
    # 提取各自的 <sheet> 块
    import re
    sheet_pattern = re.compile(r"(<sheet\b.*?</sheet>)", re.DOTALL)
    down_sheet = sheet_pattern.search(down_xml)
    up_sheet = sheet_pattern.search(up_xml)

    combined_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<xmap-content xmlns="urn:xmind:xmap:xmlns:content:2.0"
              xmlns:fo="http://www.w3.org/1999/XSL/Format"
              xmlns:svg="http://www.w3.org/2000/svg"
              xmlns:xhtml="http://www.w3.org/1999/xhtml"
              xmlns:xlink="http://www.w3.org/1999/xlink"
              version="2.0">
{down_sheet.group(1) if down_sheet else ""}
{up_sheet.group(1) if up_sheet else ""}
</xmap-content>
"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content.xml", combined_xml.encode("utf-8"))
        zf.writestr("meta.xml", _META_XML)
        zf.writestr("META-INF/container.xml", _CONTAINER_XML)
        zf.writestr("manifest.json", _MANIFEST_JSON)

    with open(output_path, "wb") as f:
        f.write(buf.getvalue())
    print(f"双向 XMind 文件已导出（2个Sheet）: {output_path}")
