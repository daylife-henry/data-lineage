"""
object_extractor.py
从 SQL 文本中提取数据库对象的定义与引用关系。

核心数据结构：
  DBObject   — 一个被定义的数据库对象（表/视图/存储过程/函数）
  Reference  — 一个对象引用了另一个对象（A 的定义体中出现了 B）
"""
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# ─────────────────────────────────────────────────────────────
# 数据结构
# ─────────────────────────────────────────────────────────────

@dataclass
class DBObject:
    """被定义的数据库对象"""
    name: str            # 归一化后的对象名（小写，去掉 schema 前缀可选）
    full_name: str       # 原始完整名（db.schema.table 或 schema.table）
    obj_type: str        # TABLE / VIEW / PROCEDURE / FUNCTION / UNKNOWN
    source_file: str     # 来源文件路径
    definition: str      # 对象定义的原始 SQL 片段（截取前 500 字符用于预览）


@dataclass
class Reference:
    """一条引用关系：source_obj 的定义体中引用了 target_obj"""
    source_name: str     # 定义者对象名（归一化）
    target_name: str     # 被引用的对象名（归一化）
    source_file: str     # 来源文件
    ref_type: str = "USE"  # USE / JOIN / INSERT_INTO / etc.


# ─────────────────────────────────────────────────────────────
# 临时表判断
# ─────────────────────────────────────────────────────────────

_TEMP_NAME_PATTERNS = (
    re.compile(r"^#{1,2}[\w$]+$", re.IGNORECASE),      # TSQL: #tmp / ##tmp
    re.compile(r"^tmp[\._].+", re.IGNORECASE),         # tmp_xxx / tmp.xxx
    re.compile(r"^temp[\._].+", re.IGNORECASE),        # temp_xxx / temp.xxx
    re.compile(r"^pg_temp\..+", re.IGNORECASE),        # Postgres 临时 schema
)


def is_temporary_name(name: str) -> bool:
    """按命名规则判断是否临时表/临时对象。"""
    norm = _normalize(name)
    if not norm:
        return False
    return any(p.match(norm) for p in _TEMP_NAME_PATTERNS)


def is_temporary_create_statement(sql_fragment: str) -> bool:
    """按 CREATE 语句关键字判断是否定义了临时表。"""
    text = sql_fragment.lower()
    return (
        "create temporary table" in text
        or "create temp table" in text
        or "create volatile table" in text
        or "create local temporary table" in text
        or "create global temporary table" in text
    )


# ─────────────────────────────────────────────────────────────
# 对象名归一化
# ─────────────────────────────────────────────────────────────

def _normalize(name: str) -> str:
    """
    归一化对象名：
      - 去除方括号、反引号、双引号包裹
      - 去掉括号及其内容（支持嵌套）
      - 去掉空格后转小写
      - 保留完整限定名（不拆分），方便后续区分跨库对象
    """
    name = name.strip()
    # 去掉方括号、反引号包裹
    while name and name[0] in '[]`"':
        name = name[1:]
    while name and name[-1] in '[]`"':
        name = name[:-1]
    # 去掉括号内容（支持嵌套括号，逐层剥除直到无括号）
    while "(" in name:
        # 找第一个 (
        p = name.index("(")
        # 找对应的 )
        depth = 0
        q = p
        for i, ch in enumerate(name[p:], p):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    q = i
                    break
        name = name[:p] + name[q + 1:]
    # 合并空格
    name = re.sub(r"\s+", "", name)
    return name.lower()


# ─────────────────────────────────────────────────────────────
# CREATE 语句解析（提取对象定义）
# ─────────────────────────────────────────────────────────────

# 匹配 CREATE [OR REPLACE] [TEMP/TEMPORARY] <TYPE> [IF NOT EXISTS] <name>
_CREATE_PATTERN = re.compile(
    r"CREATE\s+"
    r"(?:OR\s+REPLACE\s+)?"
    r"(?:TEMP(?:ORARY)?\s+)?"
    r"(TABLE|VIEW|PROCEDURE|PROC|FUNCTION|MACRO)\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?"
    r"([#\w\.\[\]`\"$]+)",
    re.IGNORECASE,
)

# ALTER TABLE
_ALTER_TABLE_PATTERN = re.compile(
    r"ALTER\s+TABLE\s+([#\w\.\[\]`\"$]+)",
    re.IGNORECASE,
)

# 类型映射（统一 PROC → PROCEDURE）
_TYPE_MAP = {
    "table": "TABLE",
    "view": "VIEW",
    "procedure": "PROCEDURE",
    "proc": "PROCEDURE",
    "function": "FUNCTION",
    "macro": "FUNCTION",
}


def extract_definitions(sql: str, source_file: str) -> List[DBObject]:
    """从 SQL 文本中提取所有 CREATE 语句定义的对象"""
    objects = []
    for m in _CREATE_PATTERN.finditer(sql):
        obj_type = _TYPE_MAP.get(m.group(1).lower(), "UNKNOWN")
        full_name = m.group(2).strip("[]`\"")
        name = _normalize(full_name)
        # 跳过空名称和太长的异常名称
        if not name or len(name) > 200:
            continue
        # 截取定义片段（从 CREATE 开始的前 500 字符）
        start = m.start()
        snippet = sql[start: start + 500].replace("\n", " ")
        objects.append(DBObject(
            name=name,
            full_name=full_name,
            obj_type=obj_type,
            source_file=source_file,
            definition=snippet,
        ))
    return objects


# ─────────────────────────────────────────────────────────────
# 引用关系提取
# ─────────────────────────────────────────────────────────────

# 匹配 FROM / JOIN / INTO / UPDATE 后面的表名（支持多段限定名和方括号）
_REF_PATTERN = re.compile(
    r"\b(?:FROM|JOIN|INTO|UPDATE|MERGE\s+INTO|MERGE)\s+"
    r"([#\w\.\[\]`\"$]+)",
    re.IGNORECASE,
)

# 匹配 EXEC / EXECUTE SP 调用
_EXEC_PATTERN = re.compile(
    r"\bEXEC(?:UTE)?\s+([#\w\.\[\]`\"$]+)",
    re.IGNORECASE,
)

# 匹配 INSERT INTO
_INSERT_PATTERN = re.compile(
    r"\bINSERT\s+(?:OVERWRITE\s+(?:TABLE\s+)?|INTO\s+)([#\w\.\[\]`\"$]+)",
    re.IGNORECASE,
)

# 匹配 WITH/CTE 定义中的别名：WITH cte AS (...), cte2 AS (...)
_CTE_ALIAS_PATTERN = re.compile(
    r"(?:\bWITH\b|,)\s*([#\w\.\[\]`\"$]+)\s+AS\s*\(",
    re.IGNORECASE,
)


def _extract_cte_aliases(body: str) -> set:
    """提取 SQL 体中 CTE 别名集合（归一化后）。"""
    aliases = set()
    for m in _CTE_ALIAS_PATTERN.finditer(body):
        name = _normalize(m.group(1))
        if name:
            aliases.add(name)
    return aliases


def _extract_refs_from_body(body: str) -> List[Tuple[str, str]]:
    """
    从一段 SQL 体中提取所有被引用的对象名。
    返回 [(ref_type, normalized_name), ...]
    """
    refs = []
    for m in _REF_PATTERN.finditer(body):
        name = _normalize(m.group(1))
        if name:
            refs.append(("USE", name))
    for m in _EXEC_PATTERN.finditer(body):
        name = _normalize(m.group(1))
        if name:
            refs.append(("EXEC", name))
    for m in _INSERT_PATTERN.finditer(body):
        name = _normalize(m.group(1))
        if name:
            refs.append(("INSERT_INTO", name))
    return refs


def extract_references(sql: str, source_file: str, defined_objects: List[DBObject]) -> List[Reference]:
    """
    提取 SQL 文件中每个定义对象引用了哪些其他对象。

    策略：
    1. 找到每个 CREATE ... AS 的"定义体"起始位置
    2. 在定义体中提取 FROM/JOIN/EXEC 等引用
    3. 生成 Reference(source=定义者, target=被引用者)
    """
    references = []

    if not defined_objects:
        # 仅分析有对象定义的血缘，避免产生匿名脚本节点（__script__）。
        return references

    # 按 CREATE 出现顺序切分 SQL，提取每个定义体
    positions = []
    for m in _CREATE_PATTERN.finditer(sql):
        positions.append(m.start())

    for i, obj in enumerate(defined_objects):
        start = positions[i]
        end = positions[i + 1] if i + 1 < len(positions) else len(sql)
        body = sql[start:end]
        cte_aliases = _extract_cte_aliases(body)

        seen_refs = set()
        for ref_type, ref_name in _extract_refs_from_body(body):
            # 排除自引用、SQL 关键字误匹配
            if ref_name == obj.name:
                continue
            if ref_name in cte_aliases:
                continue
            if ref_name in _SQL_KEYWORDS:
                continue
            key = (obj.name, ref_name)
            if key in seen_refs:
                continue
            seen_refs.add(key)
            references.append(Reference(
                source_name=obj.name,
                target_name=ref_name,
                source_file=source_file,
                ref_type=ref_type,
            ))

    return references


# 常见 SQL 关键字，避免把它们误识别为对象名
_SQL_KEYWORDS = {
    "select", "where", "and", "or", "not", "null", "true", "false",
    "case", "when", "then", "else", "end", "as", "on", "set",
    "values", "with", "cte", "dual", "sysibm", "information_schema",
}
