"""
sql_parser.py
主解析入口：整合 sqlglot 解析 + 正则补充，
并支持从 SQL / Python / Shell 文件中提取 SQL 进行血缘分析。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import List, Tuple, Optional

# sqlglot 可选（未安装时退回纯正则模式）
try:
    import sqlglot
    import sqlglot.expressions as exp
    HAS_SQLGLOT = True
except ImportError:
    HAS_SQLGLOT = False
    print("[警告] sqlglot 未安装，将使用纯正则解析（精度较低）")

from parser.object_extractor import (
    DBObject,
    Reference,
    extract_definitions,
    extract_references,
    _normalize,
    is_temporary_name,
    is_temporary_create_statement,
)
from scanner.file_collector import FileRecord


_TEMP_CREATE_PATTERN = re.compile(
    r"create\s+(?:local\s+|global\s+)?(?:temporary|temp|volatile)\s+table\s+([#\w\.\[\]`\"$]+)",
    re.IGNORECASE,
)
_TEMP_HASH_CREATE_PATTERN = re.compile(
    r"create\s+table\s+(#{1,2}[\w$]+)",
    re.IGNORECASE,
)


def _scan_temp_names_from_sql(sql: str) -> set:
    names = set()
    for p in (_TEMP_CREATE_PATTERN, _TEMP_HASH_CREATE_PATTERN):
        for m in p.finditer(sql):
            raw = m.group(1)
            norm = _normalize(raw)
            if norm:
                names.add(norm)
                names.add(norm.lstrip("#"))
    return names


# ─────────────────────────────────────────────────────────────
# sqlglot 精确解析
# ─────────────────────────────────────────────────────────────

# 方言映射：配置文件中的方言名 → sqlglot dialect 名
DIALECT_MAP = {
    "tsql": "tsql",        # SQL Server / Azure Synapse
    "hive": "hive",        # Hive / Spark SQL
    "spark": "spark",
    "mysql": "mysql",
    "postgres": "postgres",
    "bigquery": "bigquery",
    "snowflake": "snowflake",
    "oracle": "oracle",
    "redshift": "redshift",
    "default": None,       # ANSI SQL
}

DIALECT_CANDIDATES = [
    "tsql",
    "hive",
    "spark",
    "mysql",
    "postgres",
    "bigquery",
    "snowflake",
    "oracle",
    "redshift",
    None,
]


def _dialect_candidates(configured: str) -> List[Optional[str]]:
    cfg = DIALECT_MAP.get((configured or "").lower(), None)
    result: List[Optional[str]] = []
    for d in [cfg] + DIALECT_CANDIDATES:
        if d not in result:
            result.append(d)
    return result


def _temp_target_from_file(source_file: str) -> str:
    """临时表引用统一归并到文件名节点。"""
    return Path(source_file).name.lower()


def _collect_cte_names(stmt: exp.Expression) -> set:
    """提取单条语句中的 CTE 别名（WITH xxx AS (...)）。"""
    cte_names = set()
    for cte in stmt.find_all(exp.CTE):
        alias_name = getattr(cte, "alias_or_name", None)
        if alias_name:
            norm = _normalize(str(alias_name))
            if norm:
                cte_names.add(norm)

        alias_expr = cte.args.get("alias")
        alias_id = getattr(alias_expr, "this", None) if alias_expr is not None else None
        alias_text = getattr(alias_id, "name", None) if alias_id is not None else None
        if alias_text:
            norm = _normalize(str(alias_text))
            if norm:
                cte_names.add(norm)

    return cte_names


def _sqlglot_parse(
    sql: str,
    dialect: Optional[str],
    source_file: str,
    pre_temp_names: Optional[set] = None,
) -> Tuple[List[DBObject], List[Reference], set]:
    """使用 sqlglot 精确解析 SQL，提取对象定义和引用关系"""
    objects: List[DBObject] = []
    references: List[Reference] = []
    temp_tables: set = set(pre_temp_names or set())

    statements = sqlglot.parse(sql, dialect=dialect, error_level=sqlglot.ErrorLevel.RAISE)

    for stmt in statements:
        if stmt is None:
            continue

        cte_names = _collect_cte_names(stmt)

        if isinstance(stmt, (exp.Create,)):
            kind = stmt.args.get("kind", "")
            kind_str = str(kind).upper() if kind else "UNKNOWN"
            if kind_str in ("PROC", "PROCEDURE"):
                kind_str = "PROCEDURE"
            elif kind_str == "MACRO":
                kind_str = "FUNCTION"

            this = stmt.args.get("this")
            if not this:
                continue

            raw_str = str(this).strip()
            norm_name = _normalize(raw_str)
            if not norm_name:
                continue
            full_name = norm_name

            # 识别临时表定义（方言关键字 + 名称规则）
            stmt_text = stmt.sql(dialect=dialect)
            is_temp_create = (
                bool(stmt.args.get("temporary"))
                or is_temporary_name(norm_name)
                or is_temporary_create_statement(stmt_text)
                or norm_name in temp_tables
                or norm_name.lstrip("#") in temp_tables
            )
            if is_temp_create:
                temp_tables.add(norm_name)
                temp_tables.add(norm_name.lstrip("#"))
            else:
                obj = DBObject(
                    name=norm_name,
                    full_name=full_name,
                    obj_type=kind_str,
                    source_file=source_file,
                    definition=stmt_text[:500],
                )
                objects.append(obj)

            source_owner = _temp_target_from_file(source_file) if is_temp_create else norm_name

            seen = set()
            for exec_node in stmt.find_all(exp.Execute):
                exec_this = exec_node.args.get("this")
                if exec_this and isinstance(exec_this, exp.Table):
                    called_name = getattr(exec_this, "name", None)
                    called_db = getattr(exec_this, "db", None)
                    if called_name:
                        called_raw = f"{called_db}.{called_name}" if called_db else called_name
                        called_norm = _normalize(called_raw)
                        if called_norm and (source_owner, called_norm) not in seen:
                            seen.add((source_owner, called_norm))
                            references.append(Reference(
                                source_name=source_owner,
                                target_name=called_norm,
                                source_file=source_file,
                                ref_type="EXEC",
                            ))

            for table_node in stmt.find_all(exp.Table):
                node_name = getattr(table_node, "name", None)
                if not node_name:
                    continue
                node_db = getattr(table_node, "db", None)
                ref_raw = f"{node_db}.{node_name}" if node_db else node_name
                ref_norm = _normalize(ref_raw)
                if not ref_norm or ref_norm == norm_name:
                    continue
                if ref_norm in cte_names:
                    continue
                if ref_norm in _SQL_KEYWORDS_SET:
                    continue

                is_temp_ref = (
                    ref_norm in temp_tables
                    or ref_norm.lstrip("#") in temp_tables
                    or is_temporary_name(ref_norm)
                )
                target = _temp_target_from_file(source_file) if is_temp_ref else ref_norm
                ref_type = "TEMP_USE" if is_temp_ref else "USE"

                key = (source_owner, target, ref_type)
                if key in seen:
                    continue
                seen.add(key)
                references.append(Reference(
                    source_name=source_owner,
                    target_name=target,
                    source_file=source_file,
                    ref_type=ref_type,
                ))

    return objects, references, temp_tables


_SQL_KEYWORDS_SET = {
    "dual", "sysibm", "information_schema", "sys", "master",
    "tempdb", "msdb", "model",
}


# ─────────────────────────────────────────────────────────────
# 纯正则解析（fallback）
# ─────────────────────────────────────────────────────────────

def _regex_parse(sql: str, source_file: str) -> Tuple[List[DBObject], List[Reference]]:
    """纯正则模式，精度较低，作为 sqlglot 失败时的兜底"""
    objects = extract_definitions(sql, source_file)
    references = extract_references(sql, source_file, objects)

    # 临时表引用只保留文件名
    temp_names = {obj.name for obj in objects if is_temporary_name(obj.name)}
    temp_names.update(_scan_temp_names_from_sql(sql))

    owner_candidates = [
        obj for obj in objects
        if obj.name not in temp_names and not is_temporary_name(obj.name)
    ]
    owner_name = ""
    for t in ("PROCEDURE", "VIEW", "FUNCTION", "TABLE"):
        hit = next((obj for obj in owner_candidates if obj.obj_type == t), None)
        if hit is not None:
            owner_name = hit.name
            break
    if not owner_name and owner_candidates:
        owner_name = owner_candidates[0].name

    normalized_refs: List[Reference] = []
    for ref in references:
        source_is_temp = (
            ref.source_name in temp_names
            or ref.source_name.lstrip("#") in temp_names
            or is_temporary_name(ref.source_name)
        )
        source_name = owner_name if (source_is_temp and owner_name) else ref.source_name

        is_temp_ref = ref.target_name in temp_names or is_temporary_name(ref.target_name)
        if is_temp_ref:
            normalized_refs.append(Reference(
                source_name=source_name,
                target_name=_temp_target_from_file(source_file),
                source_file=ref.source_file,
                ref_type="TEMP_USE",
            ))
        else:
            normalized_refs.append(Reference(
                source_name=source_name,
                target_name=ref.target_name,
                source_file=ref.source_file,
                ref_type=ref.ref_type,
            ))

    # 临时表定义节点不入图
    normal_objects = [
        obj for obj in objects
        if obj.name not in temp_names and not is_temporary_name(obj.name)
    ]
    return normal_objects, normalized_refs


# ─────────────────────────────────────────────────────────────
# 多语言 SQL 提取
# ─────────────────────────────────────────────────────────────

_SQL_HINT = re.compile(r"\b(select|insert|update|delete|merge|create|alter|drop|with|from|join|into)\b", re.IGNORECASE)


def _looks_like_sql(text: str) -> bool:
    s = text.strip()
    if len(s) < 12:
        return False
    return bool(_SQL_HINT.search(s))


def _extract_sql_from_python(content: str) -> Tuple[List[str], List[str]]:
    snippets: List[str] = []
    issues: List[str] = []

    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if _looks_like_sql(node.value):
                    snippets.append(node.value)
            elif isinstance(node, ast.JoinedStr):
                parts: List[str] = []
                for value in node.values:
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        parts.append(value.value)
                combined = " ".join(parts)
                if _looks_like_sql(combined):
                    snippets.append(combined)
    except SyntaxError as e:
        issues.append(f"Python AST 解析失败: {e}")

    # 兜底：正则提取长字符串
    for m in re.finditer(r"([\"']{3})([\s\S]*?)\1", content):
        text = m.group(2)
        if _looks_like_sql(text):
            snippets.append(text)

    # 去重保序
    dedup: List[str] = []
    seen = set()
    for s in snippets:
        key = s.strip()
        if key and key not in seen:
            seen.add(key)
            dedup.append(key)
    return dedup, issues


def _extract_sql_from_shell(content: str) -> List[str]:
    snippets: List[str] = []

    # Heredoc: <<SQL ... SQL
    for m in re.finditer(r"<<\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?\s*\n([\s\S]*?)\n\1", content):
        body = m.group(2)
        if _looks_like_sql(body):
            snippets.append(body)

    # -c "...sql..." / -e "...sql..."
    for m in re.finditer(r"\s-[ce]\s+([\"'])([\s\S]*?)\1", content):
        body = m.group(2)
        if _looks_like_sql(body):
            snippets.append(body)

    return snippets


def _parse_sql_best_effort(sql: str, source_file: str, dialect: str) -> Tuple[List[DBObject], List[Reference], List[str]]:
    issues: List[str] = []
    if not sql.strip():
        return [], [], issues

    if not HAS_SQLGLOT:
        objs, refs = _regex_parse(sql, source_file)
        return objs, refs, issues

    best_objs: List[DBObject] = []
    best_refs: List[Reference] = []
    success = False
    last_error = ""
    pre_temp_names = _scan_temp_names_from_sql(sql)

    for d in _dialect_candidates(dialect):
        try:
            objs, refs, _ = _sqlglot_parse(sql, d, source_file, pre_temp_names=pre_temp_names)
            score = len(objs) + len(refs)
            best_score = len(best_objs) + len(best_refs)
            if score >= best_score:
                best_objs, best_refs = objs, refs
            success = True
            if score > 0:
                break
        except Exception as e:
            d_name = d or "default"
            last_error = f"sqlglot({d_name}) 失败: {e}"

    if not success:
        objs, refs = _regex_parse(sql, source_file)
        if last_error:
            if objs or refs:
                issues.append(f"{last_error}；已使用正则兜底")
            else:
                issues.append(last_error)
        return objs, refs, issues

    if not best_objs:
        reg_objs, reg_refs = _regex_parse(sql, source_file)
        best_objs.extend(reg_objs)
        best_refs.extend(reg_refs)

    return best_objs, best_refs, issues


# ─────────────────────────────────────────────────────────────
# 对外接口
# ─────────────────────────────────────────────────────────────

def parse_file(
    record: FileRecord,
    dialect: str = "default",
) -> Tuple[List[DBObject], List[Reference], List[str]]:
    """
    解析单个文件，返回 (对象列表, 引用关系列表, 错误列表)。
    """
    issues: List[str] = []

    if record.error:
        msg = f"读取失败: {record.error}"
        issues.append(msg)
        return [], [], issues

    language = (record.language or "sql").lower()

    if language == "sql":
        return _parse_sql_best_effort(record.cleaned_content, record.path, dialect)

    if language == "python":
        snippets, py_issues = _extract_sql_from_python(record.raw_content)
        issues.extend(py_issues)
    elif language == "shell":
        snippets = _extract_sql_from_shell(record.raw_content)
    else:
        return [], [], issues

    all_objects: List[DBObject] = []
    all_refs: List[Reference] = []
    for idx, snippet in enumerate(snippets, 1):
        objs, refs, sub_issues = _parse_sql_best_effort(snippet, record.path, dialect)
        all_objects.extend(objs)
        all_refs.extend(refs)
        issues.extend([f"snippet#{idx}: {x}" for x in sub_issues])

    # 去重
    uniq_objs = {}
    for obj in all_objects:
        uniq_objs[(obj.name, obj.source_file)] = obj

    uniq_refs = {}
    for ref in all_refs:
        key = (ref.source_name, ref.target_name, ref.source_file, ref.ref_type)
        uniq_refs[key] = ref

    return list(uniq_objs.values()), list(uniq_refs.values()), issues


def parse_all(
    records: List[FileRecord],
    dialect: str = "default",
    verbose: bool = True,
) -> Tuple[List[DBObject], List[Reference], List[dict]]:
    """
    批量解析所有文件。

    :return: (所有对象, 所有引用关系, 错误列表)
    """
    all_objects: List[DBObject] = []
    all_refs: List[Reference] = []
    all_errors: List[dict] = []

    total = len(records)
    for i, rec in enumerate(records, 1):
        if verbose:
            print(f"  [{i}/{total}] Parsing: {rec.relative_path}")
        objs, refs, issues = parse_file(rec, dialect)
        all_objects.extend(objs)
        all_refs.extend(refs)
        for msg in issues:
            all_errors.append({"file": rec.path, "reason": msg})

    if verbose:
        print(f"\nParsed: {len(all_objects)} objects, {len(all_refs)} references")
        if all_errors:
            print(f"  With {len(all_errors)} parse/read issues (继续执行)")

    return all_objects, all_refs, all_errors
