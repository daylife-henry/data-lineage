"""
routes/search.py — 搜索相关接口
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from api.state import AppState

router = APIRouter()


@router.get("/search", summary="搜索数据库对象")
def search_objects(
    keyword: str = Query(..., description="对象名关键词（支持部分匹配）"),
    limit: int = Query(50, ge=1, le=200, description="最多返回条数"),
):
    """
    按关键词搜索数据库对象，返回匹配列表。
    """
    state = AppState.get()
    state.refresh_graph_if_needed()
    if state.graph is None:
        raise HTTPException(status_code=503, detail="图未加载，请先运行 scan.py")
    results = state.graph.search_nodes(keyword, limit=limit)
    return {"keyword": keyword, "count": len(results), "results": results}


@router.get("/lineage/dependents", summary="查询谁引用了该对象（下游调用链）")
def get_dependents(
    name: str = Query(..., description="对象名（归一化后的小写名）"),
    max_depth: int = Query(10, ge=1, le=50, description="最大递归深度"),
):
    """
    返回「谁引用了 name」的完整嵌套树（下游调用链）。
    例：搜索 A，返回 A→B→C 的树形结构。
    """
    state = AppState.get()
    state.refresh_graph_if_needed()
    if state.graph is None:
        raise HTTPException(status_code=503, detail="图未加载，请先运行 scan.py")
    tree = state.graph.get_dependents_tree(name.lower(), max_depth=max_depth)
    return {"direction": "dependents", "root": name, "tree": tree}


@router.get("/lineage/dependencies", summary="查询该对象依赖了谁（上游依赖链）")
def get_dependencies(
    name: str = Query(..., description="对象名（归一化后的小写名）"),
    max_depth: int = Query(10, ge=1, le=50, description="最大递归深度"),
):
    """
    返回「name 依赖了哪些对象」的完整嵌套树（上游依赖链）。
    """
    state = AppState.get()
    state.refresh_graph_if_needed()
    if state.graph is None:
        raise HTTPException(status_code=503, detail="图未加载，请先运行 scan.py")
    tree = state.graph.get_dependencies_tree(name.lower(), max_depth=max_depth)
    return {"direction": "dependencies", "root": name, "tree": tree}


@router.get("/object/{name}", summary="获取单个对象详情")
def get_object(name: str):
    """获取指定对象的元信息"""
    state = AppState.get()
    state.refresh_graph_if_needed()
    if state.graph is None:
        raise HTTPException(status_code=503, detail="图未加载")
    info = state.graph.get_node_info(name.lower())
    if info is None:
        raise HTTPException(status_code=404, detail=f"对象不存在: {name}")
    return info
