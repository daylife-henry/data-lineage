"""
db_store.py
将解析结果（对象 + 引用关系）持久化到 SQLite，
支持增量更新和重新加载到内存图。
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import List, Tuple

from parser.object_extractor import DBObject, Reference
from graph.lineage_graph import LineageGraph


DEFAULT_DB_PATH = "lineage.db"


def init_db(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """初始化 SQLite 数据库，创建表结构"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS db_objects (
            name        TEXT NOT NULL,
            full_name   TEXT,
            obj_type    TEXT,
            source_file TEXT,
            definition  TEXT,
            PRIMARY KEY (name, source_file)
        );

        CREATE TABLE IF NOT EXISTS db_references (
            source_name TEXT NOT NULL,
            target_name TEXT NOT NULL,
            source_file TEXT,
            ref_type    TEXT,
            PRIMARY KEY (source_name, target_name, source_file)
        );

        CREATE INDEX IF NOT EXISTS idx_obj_name ON db_objects(name);
        CREATE INDEX IF NOT EXISTS idx_ref_source ON db_references(source_name);
        CREATE INDEX IF NOT EXISTS idx_ref_target ON db_references(target_name);
    """)
    conn.commit()
    return conn


def save_objects(conn: sqlite3.Connection, objects: List[DBObject]) -> None:
    """批量写入对象（INSERT OR REPLACE）"""
    rows = [
        (obj.name, obj.full_name, obj.obj_type, obj.source_file, obj.definition)
        for obj in objects
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO db_objects (name, full_name, obj_type, source_file, definition) VALUES (?,?,?,?,?)",
        rows,
    )
    conn.commit()


def save_references(conn: sqlite3.Connection, refs: List[Reference]) -> None:
    """批量写入引用关系（INSERT OR REPLACE）"""
    rows = [
        (ref.source_name, ref.target_name, ref.source_file, ref.ref_type)
        for ref in refs
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO db_references (source_name, target_name, source_file, ref_type) VALUES (?,?,?,?)",
        rows,
    )
    conn.commit()


def load_graph(conn: sqlite3.Connection) -> LineageGraph:
    """从 SQLite 重建内存血缘图"""
    graph = LineageGraph()

    # 加载所有对象
    objects = []
    for row in conn.execute("SELECT name, full_name, obj_type, source_file, definition FROM db_objects"):
        objects.append(DBObject(
            name=row["name"],
            full_name=row["full_name"] or row["name"],
            obj_type=row["obj_type"] or "UNKNOWN",
            source_file=row["source_file"] or "",
            definition=row["definition"] or "",
        ))
    graph.add_objects(objects)

    # 加载所有引用关系
    refs = []
    for row in conn.execute("SELECT source_name, target_name, source_file, ref_type FROM db_references"):
        refs.append(Reference(
            source_name=row["source_name"],
            target_name=row["target_name"],
            source_file=row["source_file"] or "",
            ref_type=row["ref_type"] or "USE",
        ))
    graph.add_references(refs)

    return graph


def clear_by_file(conn: sqlite3.Connection, source_file: str) -> None:
    """
    删除某个文件对应的所有对象和引用（用于增量更新时先清除旧数据）。
    """
    conn.execute("DELETE FROM db_objects WHERE source_file = ?", (source_file,))
    conn.execute("DELETE FROM db_references WHERE source_file = ?", (source_file,))
    conn.commit()


def clear_all(conn: sqlite3.Connection) -> None:
    """清空所有对象和引用（用于全量重建）。"""
    conn.execute("DELETE FROM db_objects")
    conn.execute("DELETE FROM db_references")
    conn.commit()


def get_stats(conn: sqlite3.Connection) -> dict:
    """返回数据库统计信息"""
    obj_count = conn.execute("SELECT COUNT(*) FROM db_objects").fetchone()[0]
    ref_count = conn.execute("SELECT COUNT(*) FROM db_references").fetchone()[0]
    type_rows = conn.execute(
        "SELECT obj_type, COUNT(*) as cnt FROM db_objects GROUP BY obj_type ORDER BY cnt DESC"
    ).fetchall()
    return {
        "object_count": obj_count,
        "reference_count": ref_count,
        "type_breakdown": {r["obj_type"]: r["cnt"] for r in type_rows},
    }
