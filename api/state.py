"""
state.py — 全局共享状态（内存图单例）
"""
from __future__ import annotations
from typing import Optional
from pathlib import Path

import yaml

from graph.lineage_graph import LineageGraph


class AppState:
    _instance: Optional["AppState"] = None

    def __init__(self):
        self.graph: Optional[LineageGraph] = None
        self.db_path: str = "lineage.db"
        self._db_mtime: Optional[float] = None

    def _resolve_db_path(self) -> Path:
        """从 config.yaml 读取数据库路径（不存在则回退 lineage.db）。"""
        default_path = Path(self.db_path)
        config_path = Path(__file__).parent.parent / "config.yaml"
        if not config_path.exists():
            return default_path

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            cfg_db = cfg.get("db_path")
            if cfg_db:
                return Path(str(cfg_db))
        except Exception:
            # 配置文件异常时保持已有路径，避免影响 API 可用性
            return default_path

        return default_path

    def refresh_graph_if_needed(self, force: bool = False) -> None:
        """当 SQLite 变更时自动刷新内存图。"""
        db_path = self._resolve_db_path()
        self.db_path = str(db_path)

        if not db_path.exists():
            self.graph = None
            self._db_mtime = None
            return

        mtime = db_path.stat().st_mtime
        if (
            not force
            and self.graph is not None
            and self._db_mtime is not None
            and mtime <= self._db_mtime
        ):
            return

        from graph.db_store import init_db, load_graph

        conn = init_db(self.db_path)
        try:
            self.graph = load_graph(conn)
        finally:
            conn.close()
        self._db_mtime = mtime

    @classmethod
    def get(cls) -> "AppState":
        if cls._instance is None:
            cls._instance = AppState()
        return cls._instance
