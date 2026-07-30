"""
file_collector.py
读取 SQL 文件内容，并做基础预处理（注释清洗、编码容错）。
返回结构化的 FileRecord 供解析器使用。
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class FileRecord:
    """单个 SQL 文件的原始记录"""
    path: str                    # 文件绝对路径
    relative_path: str           # 相对于仓库根的路径（用于展示）
    raw_content: str             # 原始文本内容
    cleaned_content: str         # 清洗后（去掉注释）的内容
    encoding: str = "utf-8"
    error: Optional[str] = None  # 读取/解码错误信息
    language: str = "sql"       # sql / python / shell / other


def _try_read(path: str) -> tuple[str, str, Optional[str]]:
    """尝试多种编码读取文件，返回 (内容, 编码, 错误)"""
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb2312", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read(), enc, None
        except (UnicodeDecodeError, LookupError):
            continue
    return "", "unknown", f"Unable to decode file: {path}"


# 去除 SQL 单行注释 (-- ...) 和块注释 (/* ... */)
_LINE_COMMENT = re.compile(r"--[^\n]*")


def _remove_block_comments(text: str) -> str:
    """移除块注释，支持嵌套块注释。"""
    out = []
    i = 0
    n = len(text)
    depth = 0

    while i < n:
        if i + 1 < n and text[i] == "/" and text[i + 1] == "*":
            depth += 1
            i += 2
            continue
        if depth > 0 and i + 1 < n and text[i] == "*" and text[i + 1] == "/":
            depth -= 1
            i += 2
            continue

        if depth == 0:
            out.append(text[i])
        i += 1

    return "".join(out)


def clean_sql(raw: str) -> str:
    """去除 SQL 注释，保留换行结构（便于后续按语句分割）"""
    text = _remove_block_comments(raw)
    text = _LINE_COMMENT.sub("", text)
    return text


def detect_language(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in {".sql", ".ddl", ".sp", ".proc", ".view", ".hql", ".bql"}:
        return "sql"
    if suffix in {".py"}:
        return "python"
    if suffix in {".sh", ".bash", ".ksh", ".zsh", ".ps1", ".bat", ".cmd"}:
        return "shell"
    return "other"


def collect_files(file_paths: List[str], repo_root: str = "") -> List[FileRecord]:
    """
    批量读取 SQL 文件，返回 FileRecord 列表。

    :param file_paths: 文件绝对路径列表（由 git_scanner 提供）
    :param repo_root:  仓库根路径，用于计算 relative_path（可为空）
    :return: FileRecord 列表
    """
    records = []
    for path in file_paths:
        raw, enc, err = _try_read(path)
        language = detect_language(path)
        # 计算相对路径
        if repo_root:
            try:
                rel = str(Path(path).relative_to(repo_root))
            except ValueError:
                rel = path
        else:
            rel = path

        if err:
            cleaned = ""
        elif language == "sql":
            cleaned = clean_sql(raw)
        else:
            cleaned = raw
        records.append(FileRecord(
            path=path,
            relative_path=rel,
            raw_content=raw,
            cleaned_content=cleaned,
            encoding=enc,
            error=err,
            language=language,
        ))
    return records


if __name__ == "__main__":
    import sys
    from scanner.git_scanner import scan_directory
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    paths = scan_directory(root)
    recs = collect_files(paths, root)
    ok = [r for r in recs if not r.error]
    bad = [r for r in recs if r.error]
    print(f"Success: {len(ok)} files, Failed: {len(bad)} files")
    for r in bad:
        print(f"  [Error] {r.path}: {r.error}")
