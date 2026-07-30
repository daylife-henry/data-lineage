"""
routes/export.py — XMind 导出接口
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from api.state import AppState
from exporter.xmind_writer import export_to_bytes

router = APIRouter()


@router.get("/export/xmind", summary="导出血缘树为 .xmind 文件")
def export_xmind(
    name: str = Query(..., description="对象名"),
    direction: str = Query("dependents", description="方向: dependents（下游）或 dependencies（上游）"),
    max_depth: int = Query(10, ge=1, le=50),
    both: bool = Query(False, description="是否同时导出上下游（两个Sheet）"),
):
    """
    导出指定对象的血缘树为 .xmind 文件，直接下载。
    """
    state = AppState.get()
    state.refresh_graph_if_needed()
    if state.graph is None:
        raise HTTPException(status_code=503, detail="图未加载，请先运行 scan.py")

    name_lower = name.lower()

    if both:
        # 上下游合并到两个 Sheet
        from exporter.xmind_writer import export_both_directions
        import io, zipfile, re

        down_tree = state.graph.get_dependents_tree(name_lower, max_depth=max_depth)
        up_tree = state.graph.get_dependencies_tree(name_lower, max_depth=max_depth)

        from exporter.xmind_writer import _build_content_xml, _META_XML, _CONTAINER_XML, _MANIFEST_JSON
        import json

        down_xml = _build_content_xml(down_tree, f"{name} — 下游", "下游（谁引用了我）")
        up_xml = _build_content_xml(up_tree, f"{name} — 上游", "上游（我依赖了谁）")

        sheet_pattern = re.compile(r"(<sheet\b.*?</sheet>)", re.DOTALL)
        down_sheet = sheet_pattern.search(down_xml)
        up_sheet = sheet_pattern.search(up_xml)

        combined = f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<xmap-content xmlns="urn:xmind:xmap:xmlns:content:2.0" version="2.0">
{down_sheet.group(1) if down_sheet else ""}
{up_sheet.group(1) if up_sheet else ""}
</xmap-content>"""

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("content.xml", combined.encode("utf-8"))
            zf.writestr("meta.xml", _META_XML)
            zf.writestr("META-INF/container.xml", _CONTAINER_XML)
            zf.writestr("manifest.json", _MANIFEST_JSON)
        xmind_bytes = buf.getvalue()
    else:
        if direction == "dependents":
            tree = state.graph.get_dependents_tree(name_lower, max_depth=max_depth)
            dir_label = "下游（谁引用了我）"
        else:
            tree = state.graph.get_dependencies_tree(name_lower, max_depth=max_depth)
            dir_label = "上游（我依赖了谁）"

        xmind_bytes = export_to_bytes(tree, sheet_title=f"{name} 血缘分析", direction=dir_label)

    filename = f"{name}_lineage.xmind"
    return Response(
        content=xmind_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
