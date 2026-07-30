# DB Lineage - 数据库对象血缘分析工具

给定本地 SQL 代码目录或 Git 仓库，自动解析 SQL/Python/Shell 中的 SQL 语句，构建数据库对象依赖图，提供 Web 可视化搜索与上下游查询，并支持导出 XMind。

---

## 目录

- [1. 项目能力总览](#1-项目能力总览)
- [2. 快速开始](#2-快速开始)
- [3. 配置说明（config.yaml）](#3-配置说明configyaml)
- [4. 运行方式与命令参数](#4-运行方式与命令参数)
- [5. Web 界面使用说明](#5-web-界面使用说明)
- [6. 解析规则（详细）](#6-解析规则详细)
- [7. 类型判定规则（含最新兜底规则）](#7-类型判定规则含最新兜底规则)
- [8. 血缘图规则与查询语义](#8-血缘图规则与查询语义)
- [9. API 说明](#9-api-说明)
- [10. 常见问题与排查](#10-常见问题与排查)
- [11. 项目结构](#11-项目结构)

---

## 1. 项目能力总览

- 多源扫描：支持多个目录同时扫描。
- 多语言抽取：支持 `.sql/.ddl/.sp/.proc/.view/.hql/.py/.sh/.ps1/.bat/.cmd` 等文件中 SQL 识别。
- 双引擎解析：优先 `sqlglot` AST 解析，失败自动回退正则兜底。
- 图数据库落盘：解析结果写入 `lineage.db`，服务启动自动加载。
- 可视化分析：前端展示 Upstream/Downstream 树，支持深度控制、缩放、字号、节点提示。
- 导出能力：支持单方向或双方向导出 `.xmind`。
- 稳定性策略：解析失败不中断整体流程，错误写入 `分析错误.log`。

---

## 2. 快速开始

### 2.1 一键方式（Windows 推荐）

1. 修改 `config.yaml` 的 `repos` 为你的代码目录。
2. 双击 `start.bat`。
3. 程序会自动：
   - 使用内置 Python 执行扫描。
   - 启动 FastAPI 服务（`http://localhost:8765`）。
   - 自动打开浏览器。

> 注意：`start.bat` 默认会先删除旧的 `lineage.db`，再执行全量扫描。

### 2.2 手动方式（命令行）

```bash
python scan.py
python -m uvicorn api.main:app --reload --port 8765 --host 127.0.0.1
```

---

## 3. 配置说明（config.yaml）

默认配置示例：

```yaml
repos:
  - "./sample_sql"

dialect: "postgres"
db_path: "lineage.db"
verbose: true

exclude_patterns:
  - ".git"
  - "node_modules"
  - "__pycache__"
  - ".venv"
  - "archive"
  - "backup"

scan_extensions:
  - ".sql"
  - ".ddl"
  - ".sp"
  - ".proc"
  - ".view"
  - ".hql"
  - ".py"
  - ".sh"
  - ".bash"
  - ".ksh"
  - ".zsh"
  - ".ps1"
  - ".bat"
  - ".cmd"
```

### 3.1 字段解释

- `repos`：要扫描的目录列表，支持相对路径和绝对路径。
- `dialect`：SQL 方言，影响 `sqlglot` 精度。
- `db_path`：SQLite 文件路径。
- `verbose`：是否输出详细扫描日志（命令行模式下可被 `--quiet` 覆盖）。
- `exclude_patterns`：路径关键词过滤，命中即跳过。
- `scan_extensions`：参与扫描的扩展名白名单。

### 3.2 方言可选值

- `tsql`
- `hive`
- `spark`
- `mysql`
- `postgres`
- `bigquery`
- `snowflake`
- `oracle`
- `redshift`
- `default`

### 3.3 如何选择 dialect（推荐）

数据库类型与 `dialect` 对照：

- SQL Server / Azure Synapse -> `tsql`
- Hive -> `hive`
- Spark SQL / Databricks -> `spark`
- MySQL / MariaDB -> `mysql`
- PostgreSQL -> `postgres`
- BigQuery -> `bigquery`
- Snowflake -> `snowflake`
- Oracle -> `oracle`
- Amazon Redshift -> `redshift`
- 无法确定 / 接近 ANSI SQL -> `default`（仅建议临时兜底）

选择顺序建议：

1. 优先看连接信息（JDBC/驱动/仓库说明）确认数据库类型。
2. 再看 SQL 关键字特征（如 `distkey/sortkey` 常见于 Redshift，`top/#temp` 常见于 TSQL）。
3. 混合仓库按目录拆分扫描，分别指定方言，避免一个方言覆盖全部脚本。

> 说明：解析器会先尝试你配置的方言，再按候选方言兜底；因此“配错不一定报错”，但精度可能下降。

示例（按目录分别扫描）：

```bash
python scan.py --repos ./sql/redshift --dialect redshift
python scan.py --repos ./sql/postgres --dialect postgres
```

---

## 4. 运行方式与命令参数

`scan.py` 支持以下参数（命令行参数优先级高于 `config.yaml`）：

```bash
python scan.py --config config.yaml
python scan.py --repos D:/repo1 D:/repo2
python scan.py --dialect tsql
python scan.py --db-path lineage.db
python scan.py --exclude .git node_modules __pycache__
python scan.py --extensions .sql .hql .py .sh
python scan.py --incremental
python scan.py --quiet
```

### 4.1 参数说明

- `--repos`：覆盖 `repos`。
- `--dialect`：覆盖 `dialect`。
- `--db-path`：覆盖 `db_path`。
- `--exclude`：覆盖 `exclude_patterns`。
- `--extensions`：覆盖 `scan_extensions`。
- `--incremental`：增量模式，仅清理并重建本次扫描文件对应的对象和关系。
- `--quiet`：安静模式，减少逐文件日志输出。

### 4.2 全量与增量差异

- 全量（默认）：会先清空数据库全部对象/关系，再写入最新结果。
- 增量（`--incremental`）：仅按本次涉及文件清理后重建，适合大仓库提速。

---

## 5. Web 界面使用说明

### 5.1 基础操作

1. 输入关键词后点击 `Search`。
2. 在左侧结果列表选择对象。
3. 在工具栏切换：
   - `Downstream`：谁引用了我。
   - `Upstream`：我依赖了谁。
4. 调整 `Depth` 控制树展开层数。
5. 使用导出按钮导出 XMind。

### 5.2 复制选中对象名称（最新）

前端已支持“复制展示面板中选中的任意对象名称”：

- 在图上点击任意节点后，该节点成为“当前选中对象”。
- 点击功能栏按钮 `复制选中对象的名字` 可复制节点名。
- 也支持快捷键 `Ctrl+C`（macOS 为 `Command+C`）复制当前选中节点名。
- 提示方式为右下角 Toast（不再使用 alert）。

> 说明：ECharts 节点文字是 Canvas 绘制，不能像普通 HTML 文本那样直接框选复制，所以采用“点击节点 + 一键复制”方案。

---

## 6. 解析规则（详细）

### 6.1 文件扫描与预处理

1. 递归扫描 `repos` 下文件。
2. 按 `scan_extensions` 过滤。
3. 按 `exclude_patterns` 剔除。
4. 文件内容读取后进入解析阶段。

### 6.2 多语言 SQL 提取

- SQL 文件：直接解析。
- Python 文件：优先 AST 提取字符串 SQL，失败时再做长字符串正则提取。
- Shell/批处理文件：支持 heredoc、`-c/-e` 形式 SQL 片段提取。

### 6.3 双引擎解析流程

1. 尝试 `sqlglot`，并按“配置方言 + 候选方言列表”逐一试解析。
2. 若 `sqlglot` 失败：
   - 自动回退到正则解析。
   - 尽量继续产出对象和引用，避免中断。
3. 若 AST 结果无对象：会追加正则补充。

### 6.4 定义与引用识别

- 识别定义对象类型：`TABLE / VIEW / PROCEDURE / FUNCTION`。
- 识别引用：`FROM/JOIN/INTO/UPDATE/MERGE/EXEC` 等。
- CTE 别名会被收集并排除，避免误识别为真实对象。
- 临时对象引用会做归并处理，尽量减少临时节点污染主图。

### 6.5 错误处理规则

- 单文件/单片段失败不会中断全局扫描。
- 所有错误会汇总写入 `分析错误.log`。

---

## 7. 类型判定规则（含最新兜底规则）

### 7.1 已定义对象

只要在代码中识别到 CREATE 定义，就使用真实类型（`TABLE/VIEW/PROCEDURE/FUNCTION`）。

### 7.2 未定义但被引用对象（原本为 UNKNOWN）

当对象只出现在引用边里、没有定义时，系统会补节点。最新规则如下：

1. 若是临时对象：保持 `UNKNOWN`。
2. 若不是临时对象且对象名不以 `_v` 结尾：兜底判定为 `TABLE`。
3. 其他情况：保持 `UNKNOWN`。

这条规则用于减少类似 `chn_mdm_prepub.prepub_network_hco` 这类真实表被显示为 `UNKNOWN` 的问题，同时不改变既有解析成功逻辑。

### 7.3 临时对象判定（节选）

命名命中以下模式之一会被视为临时对象：

- `#tmp` / `##tmp`（TSQL）
- `tmp_xxx` / `tmp.xxx`
- `temp_xxx` / `temp.xxx`
- `pg_temp.xxx`

此外，`CREATE TEMP/TEMPORARY/VOLATILE TABLE` 语句也会被识别为临时定义。

---

## 8. 血缘图规则与查询语义

### 8.1 边方向定义

边采用：`被引用者 -> 引用者`。

即 `A -> B` 表示：B 引用了 A，B 是 A 的下游。

### 8.2 查询语义

- `dependents`（下游）：从节点沿 `successors` 查找“谁在用我”。
- `dependencies`（上游）：从节点沿 `predecessors` 查找“我用了谁”。

### 8.3 深度与循环

- `max_depth` 控制树展开层数。
- 遇到循环依赖会打 `_cycle` 标记，前端红色提示。

---

## 9. API 说明

服务启动后可访问：`http://localhost:8765/docs`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/search` | 按关键词搜索对象 |
| GET | `/api/lineage/dependents` | 查询下游调用链 |
| GET | `/api/lineage/dependencies` | 查询上游依赖链 |
| GET | `/api/object/{name}` | 查询单对象详情 |
| GET | `/api/export/xmind` | 导出 XMind（支持 `both=true`） |
| GET | `/api/stats` | 返回节点数、边数、类型分布 |

示例：

```http
GET /api/search?keyword=orders&limit=100
GET /api/lineage/dependents?name=fact_orders&max_depth=5
GET /api/lineage/dependencies?name=v_region_sales&max_depth=5
GET /api/export/xmind?name=fact_orders&both=true&max_depth=5
```

---

## 10. 常见问题与排查

### 10.1 为什么看到 UNKNOWN？

常见原因：

- 对象定义不在扫描范围内（`repos` 未覆盖）。
- 文件扩展名不在 `scan_extensions`。
- SQL 语法复杂，AST 与正则都未识别到定义。

排查建议：

1. 检查 `repos` 是否包含定义文件所在目录。
2. 检查扩展名是否被纳入扫描。
3. 查看 `分析错误.log`。
4. 必要时调大日志（不要 `--quiet`）并重扫。

### 10.2 修改了 SQL，但前端没更新？

- 请先重新执行 `scan.py`。
- API 层会按 `lineage.db` 的修改时间自动刷新内存图。

### 10.3 复制功能为什么不是框选文本？

- 图节点为 Canvas 渲染，不支持原生文本框选。
- 正确方式：点击节点选中，再点 `复制选中对象的名字` 或按 `Ctrl+C`。

---

## 11. 项目结构

```text
db-lineage/
├─ config.yaml
├─ scan.py
├─ start.bat
├─ requirements.txt
├─ lineage.db
├─ 分析错误.log
├─ api/
│  ├─ main.py
│  ├─ state.py
│  └─ routes/
│     ├─ search.py
│     └─ export.py
├─ parser/
│  ├─ sql_parser.py
│  └─ object_extractor.py
├─ scanner/
│  ├─ git_scanner.py
│  └─ file_collector.py
├─ graph/
│  ├─ lineage_graph.py
│  └─ db_store.py
├─ exporter/
│  └─ xmind_writer.py
├─ frontend/
│  └─ index.html
└─ sample_sql/
```

---

## 版本说明（本次更新）

本 README 已按最新规则更新，重点包含：

- 展示面板节点选中复制机制（按钮 + 快捷键 + Toast）。
- UNKNOWN 类型兜底规则：非临时且不以 `_v` 结尾时，判定为 TABLE。
- 配置项、参数优先级、增量/全量模式、排查建议的详细说明。
