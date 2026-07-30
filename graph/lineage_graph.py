"""
lineage_graph.py
使用 NetworkX 构建有向血缘图，并持久化到 SQLite。

图方向约定：
  edge A → B 表示"B 引用了 A"（B 依赖 A，B 是 A 的下游）
  等价于：A 被 B 调用

这样，给定节点 A，找其所有后继（successors）= 谁调用了 A（下游调用链）。
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Any

try:
    import networkx as nx
    HAS_NX = True
except ImportError:
    HAS_NX = False
    print("[警告] NetworkX 未安装，血缘图功能不可用。请运行: pip install networkx")

from parser.object_extractor import DBObject, Reference, is_temporary_name


# ─────────────────────────────────────────────────────────────
# 血缘图核心类
# ─────────────────────────────────────────────────────────────

class LineageGraph:
    """
    有向血缘图。
    节点属性：name, obj_type, source_file, full_name
    边属性：ref_type, source_file
    """

    def __init__(self):
        if not HAS_NX:
            raise RuntimeError("NetworkX 未安装，请先 pip install networkx")
        self.G: nx.DiGraph = nx.DiGraph()
        # 对象元信息索引：name → DBObject
        self._obj_meta: Dict[str, DBObject] = {}

    # ── 构建 ──────────────────────────────────────────────────

    def add_objects(self, objects: List[DBObject]) -> None:
        """批量添加对象节点（会覆盖已有节点的元信息）"""
        for obj in objects:
            self._obj_meta[obj.name] = obj
            self.G.add_node(
                obj.name,
                obj_type=obj.obj_type,
                source_file=obj.source_file,
                full_name=obj.full_name,
            )

    def add_references(self, refs: List[Reference]) -> None:
        """
        批量添加引用边。
        方向：target → source（target 被 source 引用，即 target 的下游是 source）
        """
        for ref in refs:
            # 兼容历史数据：跳过匿名脚本来源，避免出现 __script__ / _script_ UNKNOWN 节点
            if ref.source_name in {"__script__", "_script_"}:
                continue
            # 确保节点存在（引用了但未定义的对象，标记为 UNKNOWN）
            if ref.source_name not in self.G:
                self.G.add_node(
                    ref.source_name,
                    obj_type=self._infer_missing_obj_type(ref.source_name),
                    source_file=ref.source_file,
                    full_name=ref.source_name,
                )
            if ref.target_name not in self.G:
                self.G.add_node(
                    ref.target_name,
                    obj_type=self._infer_missing_obj_type(ref.target_name),
                    source_file="",
                    full_name=ref.target_name,
                )

            # edge: target → source（target 的"被调用者"列表包含 source）
            self.G.add_edge(
                ref.target_name,
                ref.source_name,
                ref_type=ref.ref_type,
                source_file=ref.source_file,
            )

    @staticmethod
    def _infer_missing_obj_type(name: str) -> str:
        """
        对未定义对象做最小兜底：
        - 临时对象仍为 UNKNOWN；
        - 非临时对象且名称不以 _v 结尾时，兜底为 TABLE；
        - 其余保持 UNKNOWN。
        """
        if not name:
            return "UNKNOWN"
        n = name.lower()
        if is_temporary_name(n):
            return "UNKNOWN"
        if not n.endswith("_v"):
            return "TABLE"
        return "UNKNOWN"

    # ── 查询 ──────────────────────────────────────────────────

    def get_node_info(self, name: str) -> Optional[Dict[str, Any]]:
        """获取节点元信息"""
        if name not in self.G:
            return None
        data = dict(self.G.nodes[name])
        data["name"] = name
        return data

    def get_dependents_tree(self, name: str, max_depth: int = 20) -> Dict:
        """
        BFS 获取「谁引用了 name」的完整嵌套树（下游调用链）。
        返回树形 dict，可直接用于 XMind 导出和前端渲染。

        结构：
        {
          "name": "A",
          "obj_type": "VIEW",
          "source_file": "...",
          "children": [
            {"name": "B", "obj_type": "SP", ..., "children": [...]},
            ...
          ]
        }
        """
        if name not in self.G:
            return {"name": name, "obj_type": "UNKNOWN", "source_file": "", "children": []}

        visited = set()

        def _build(node: str, depth: int) -> Dict:
            node_info = self.get_node_info(node) or {}
            result = {
                "name": node,
                "obj_type": node_info.get("obj_type", "UNKNOWN"),
                "source_file": node_info.get("source_file", ""),
                "full_name": node_info.get("full_name", node),
                "children": [],
            }
            if depth >= max_depth:
                return result
            visited.add(node)
            for successor in sorted(self.G.successors(node)):
                if successor in visited:
                    succ_info = self.get_node_info(successor)
                    succ_type = (succ_info or {}).get("obj_type", "UNKNOWN")
                    result["children"].append({
                        "name": successor,
                        "obj_type": succ_type,
                        "source_file": (succ_info or {}).get("source_file", ""),
                        "full_name": successor,
                        "children": [],
                        "_cycle": True,
                    })
                else:
                    result["children"].append(_build(successor, depth + 1))
            visited.discard(node)
            return result

        return _build(name, 0)

    def get_dependencies_tree(self, name: str, max_depth: int = 20) -> Dict:
        """
        BFS 获取「name 引用了哪些对象」的完整嵌套树（上游依赖链）。
        与 get_dependents_tree 方向相反（沿边反向遍历）。
        """
        if name not in self.G:
            return {"name": name, "obj_type": "UNKNOWN", "source_file": "", "children": []}

        visited = set()

        def _build(node: str, depth: int) -> Dict:
            node_info = self.get_node_info(node) or {}
            result = {
                "name": node,
                "obj_type": node_info.get("obj_type", "UNKNOWN"),
                "source_file": node_info.get("source_file", ""),
                "full_name": node_info.get("full_name", node),
                "children": [],
            }
            if depth >= max_depth:
                return result
            visited.add(node)
            for predecessor in sorted(self.G.predecessors(node)):
                if predecessor in visited:
                    result["children"].append({
                        "name": predecessor,
                        "obj_type": "UNKNOWN",
                        "source_file": "",
                        "full_name": predecessor,
                        "children": [],
                        "_cycle": True,
                    })
                else:
                    result["children"].append(_build(predecessor, depth + 1))
            visited.discard(node)
            return result

        return _build(name, 0)

    def search_nodes(self, keyword: str, limit: int = 50) -> List[Dict]:
        """
        按关键词模糊搜索节点名（大小写不敏感，支持部分匹配）。
        返回匹配节点的信息列表，按名称排序。
        """
        kw = keyword.lower()
        results = []
        for node in self.G.nodes:
            if kw in node.lower():
                info = self.get_node_info(node)
                if info:
                    results.append(info)
        results.sort(key=lambda x: (x.get("obj_type", ""), x["name"]))
        return results[:limit]

    # ── 统计 ──────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        """返回图统计信息"""
        type_count: Dict[str, int] = {}
        for _, data in self.G.nodes(data=True):
            t = data.get("obj_type", "UNKNOWN")
            type_count[t] = type_count.get(t, 0) + 1
        return {
            "node_count": self.G.number_of_nodes(),
            "edge_count": self.G.number_of_edges(),
            "type_breakdown": type_count,
        }
