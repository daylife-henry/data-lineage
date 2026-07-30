"""
scan.py — 主扫描脚本
使用方式：
  python scan.py                    # 使用 config.yaml 配置
  python scan.py --repos ./my-sql   # 命令行指定目录
  python scan.py --dialect hive     # 指定方言
  python scan.py --incremental      # 增量模式（只扫描新增/变更文件）
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime
import yaml
from pathlib import Path

# 确保项目根在 sys.path
PROJECT_ROOT = str(Path(__file__).parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scanner.git_scanner import scan_multiple
from scanner.file_collector import collect_files
from parser.sql_parser import parse_all
from graph.db_store import init_db, save_objects, save_references, clear_by_file, clear_all
from graph.lineage_graph import LineageGraph


ERROR_LOG_FILE = "分析错误.log"


def _write_error_log(entries: list[dict], error_log_path: str = ERROR_LOG_FILE) -> None:
    """写入分析错误日志（覆盖写）。"""
    p = Path(error_log_path)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"[{ts}] 解析/分析错误日志", ""]
    if not entries:
        lines.append("无错误。")
    else:
        for idx, item in enumerate(entries, 1):
            reason = str(item.get("reason", "")).replace("\r", " ").replace("\n", " ")
            reason = re.sub(r"\x1b\[[0-9;]*m", "", reason)
            lines.append(f"{idx}. 文件: {item.get('file', '')}")
            lines.append(f"   原因: {reason}")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_scan(repos: list, dialect: str, db_path: str,
             exclude_patterns: list = None, sql_extensions: list = None,
             verbose: bool = True, incremental: bool = False):
    t0 = time.time()
    print(f"=== DB Lineage Scan Started ===")
    print(f"Repos: {repos}")
    print(f"Dialect: {dialect}")
    print(f"DB Path: {db_path}")
    print(f"Exclude: {exclude_patterns}")
    print(f"Extensions: {sql_extensions}")
    print()

    analysis_errors: list[dict] = []

    # 1. Scan files
    print("[1/4] Scanning source files...")
    extensions_set = set(sql_extensions) if sql_extensions else None
    try:
        files = scan_multiple(repos, extensions=extensions_set)
    except Exception as e:
        analysis_errors.append({"file": ",".join(repos), "reason": f"扫描目录失败: {e}"})
        files = []
    
    # 过滤排除模式
    if exclude_patterns:
        files = [f for f in files if not any(p in f for p in exclude_patterns)]
    
    print(f"  Found {len(files)} files")

    if verbose:
        for f in files[:5]:
            print(f"    {f}")
        if len(files) > 5:
            print(f"    ... and {len(files) - 5} more")

    # 2. Read file contents
    print("\n[2/4] Reading source files...")
    repo_root = str(Path(repos[0]).resolve()) if repos else ""
    records = collect_files(files, repo_root=repo_root)
    for rec in records:
        if rec.error:
            analysis_errors.append({"file": rec.path, "reason": rec.error})
    print(f"  Read {len(records)} files")

    # 3. Parse SQL
    print("\n[3/4] Parsing SQL files...")
    objects, references, parse_errors = parse_all(records, dialect=dialect, verbose=verbose)
    analysis_errors.extend(parse_errors)

    # 4. Save to database
    print("\n[4/4] Saving to SQLite...")
    stats = {"node_count": 0, "edge_count": 0}
    try:
        conn = init_db(db_path)

        # 全量模式先清空旧数据，避免历史脏引用残留
        if not incremental:
            clear_all(conn)
        # 增量模式按文件清理
        else:
            for rec in records:
                clear_by_file(conn, rec.path)

        save_objects(conn, objects)
        save_references(conn, references)

        # 加载到图中进行统计
        from graph.db_store import load_graph
        graph = load_graph(conn)
        stats = graph.stats()
        conn.close()
    except Exception as e:
        analysis_errors.append({"file": db_path, "reason": f"写入/加载数据库失败: {e}"})

    _write_error_log(analysis_errors)

    elapsed = time.time() - t0
    print(f"\n=== Scan Complete ({elapsed:.1f}s) ===")
    print(f"  Objects: {stats['node_count']}")
    print(f"  References: {stats['edge_count']}")
    print(f"  Errors: {len(analysis_errors)} (详见 {ERROR_LOG_FILE})")
    print(f"\nStart Web UI:")
    print(f"  python -m uvicorn api.main:app --reload --port 8765")


def main():
    parser = argparse.ArgumentParser(description="DB Lineage Scanner")
    parser.add_argument("--config", default="config.yaml", help="Config file path")
    parser.add_argument("--repos", nargs="+", help="Repo directories (overrides config)")
    parser.add_argument("--dialect", help="SQL dialect (overrides config)")
    parser.add_argument("--db-path", help="SQLite DB path (overrides config)")
    parser.add_argument("--exclude", nargs="+", help="Exclude patterns (overrides config)")
    parser.add_argument("--extensions", nargs="+", help="SQL extensions (overrides config)")
    parser.add_argument("--incremental", action="store_true", help="Incremental mode")
    parser.add_argument("--quiet", action="store_true", help="Quiet mode")
    args = parser.parse_args()

    # Load config
    config_path = Path(args.config)
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    else:
        cfg = {}

    repos = args.repos if args.repos else cfg.get("repos", ["./sample_sql"])
    dialect = args.dialect or cfg.get("dialect", "tsql")
    db_path = args.db_path or cfg.get("db_path", "lineage.db")
    exclude = args.exclude if args.exclude else cfg.get("exclude_patterns", [".git", "node_modules", "__pycache__", ".venv"])
    default_ext = [".sql", ".ddl", ".sp", ".proc", ".view", ".hql", ".py", ".sh", ".bash", ".ksh", ".zsh", ".ps1", ".bat", ".cmd"]
    extensions = args.extensions if args.extensions else cfg.get("scan_extensions", cfg.get("sql_extensions", default_ext))
    verbose = not args.quiet

    run_scan(repos, dialect, db_path,
             exclude_patterns=exclude,
             sql_extensions=extensions,
             verbose=verbose,
             incremental=args.incremental)


if __name__ == "__main__":
    main()
