"""
git_scanner.py
扫描 Git 仓库（或普通目录），收集所有 SQL 文件路径。
支持配置多个仓库 / 目录，支持 glob 过滤扩展名。
"""
import os
from pathlib import Path
from typing import List, Optional

# 可选依赖：GitPython，如果未安装则只支持本地目录扫描
try:
    import git
    HAS_GIT = True
except ImportError:
    HAS_GIT = False

# 默认识别的可扫描扩展名（SQL + Python + Shell）
DEFAULT_SCAN_EXTENSIONS = {
    ".sql", ".ddl", ".sp", ".proc", ".view", ".hql", ".bql",
    ".py", ".sh", ".bash", ".ksh", ".zsh", ".ps1", ".bat", ".cmd",
}


def scan_directory(
    root: str,
    extensions: Optional[set] = None,
    exclude_patterns: Optional[List[str]] = None,
) -> List[str]:
    """
    递归扫描 root 目录，返回所有匹配扩展名的文件绝对路径列表。

    :param root: 根目录路径（本地 Git 仓库根 或 普通目录）
    :param extensions: 要扫描的文件扩展名集合，默认使用 DEFAULT_SCAN_EXTENSIONS
    :param exclude_patterns: 要排除的目录/文件名关键词列表（模糊匹配路径）
    :return: 文件绝对路径列表
    """
    if extensions is None:
        extensions = DEFAULT_SCAN_EXTENSIONS
    if exclude_patterns is None:
        exclude_patterns = [".git", "node_modules", "__pycache__", ".venv"]

    root_path = Path(root).resolve()
    if not root_path.exists():
        raise FileNotFoundError(f"目录不存在: {root_path}")

    result = []
    for file_path in root_path.rglob("*"):
        # 跳过目录本身
        if not file_path.is_file():
            continue
        # 排除不需要的路径
        path_str = str(file_path)
        if any(pat in path_str for pat in exclude_patterns):
            continue
        # 匹配扩展名（大小写不敏感）
        if file_path.suffix.lower() in extensions:
            result.append(str(file_path))

    return sorted(result)


def scan_git_repo(
    repo_path: str,
    branch: str = "HEAD",
    extensions: Optional[set] = None,
) -> List[str]:
    """
    通过 GitPython 扫描 Git 仓库，返回指定 branch 下所有匹配文件的绝对路径。
    如果 GitPython 未安装，自动退回到普通目录扫描。

    :param repo_path: Git 仓库本地路径
    :param branch: 分支名称，默认 HEAD（当前分支）
    :param extensions: 要扫描的文件扩展名集合
    :return: 文件绝对路径列表
    """
    if not HAS_GIT:
        print("[警告] GitPython 未安装，使用普通目录扫描替代")
        return scan_directory(repo_path, extensions)

    if extensions is None:
        extensions = DEFAULT_SCAN_EXTENSIONS

    repo = git.Repo(repo_path)
    try:
        commit = repo.commit(branch)
    except Exception:
        print(f"[警告] 分支 {branch} 不存在，使用 HEAD")
        commit = repo.head.commit

    result = []
    for blob in commit.tree.traverse():
        if blob.type != "blob":
            continue
        ext = Path(blob.path).suffix.lower()
        if ext in extensions:
            abs_path = os.path.join(repo_path, blob.path)
            result.append(abs_path)

    return sorted(result)


def scan_multiple(
    paths: List[str],
    extensions: Optional[set] = None,
) -> List[str]:
    """
    扫描多个目录或 Git 仓库，合并去重返回所有 SQL 文件路径。

    :param paths: 目录/仓库路径列表
    :param extensions: 文件扩展名集合
    :return: 去重后的文件路径列表
    """
    all_files = []
    for p in paths:
        files = scan_directory(p, extensions)
        all_files.extend(files)
    # 去重，保留顺序
    seen = set()
    deduped = []
    for f in all_files:
        if f not in seen:
            seen.add(f)
            deduped.append(f)
    return deduped


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    files = scan_directory(target)
    print(f"共扫描到 {len(files)} 个 SQL 文件：")
    for f in files:
        print(" ", f)
