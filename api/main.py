"""
main.py — FastAPI 应用入口
运行方式: python -m uvicorn api.main:app --reload --port 8765
"""
from __future__ import annotations

from pathlib import Path
import yaml

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response

from api.routes.search import router as search_router
from api.routes.export import router as export_router
from api.state import AppState

app = FastAPI(
    title="DB Lineage Analyzer",
    description="数据库对象血缘分析工具 API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载前端静态文件
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

app.include_router(search_router, prefix="/api")
app.include_router(export_router, prefix="/api")


@app.get("/", include_in_schema=False)
def index():
    """返回前端 HTML（禁用缓存，确保每次都加载最新版本）"""
    html_path = frontend_dir / "index.html"
    if html_path.exists():
        content = html_path.read_bytes()
        return Response(
            content=content,
            media_type="text/html; charset=utf-8",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    return {"message": "DB Lineage API is running. 前端文件未找到，请检查 frontend/index.html"}


@app.get("/api/stats")
def get_stats():
    """返回当前已加载图的统计信息"""
    state = AppState.get()
    state.refresh_graph_if_needed()
    if state.graph is None:
        return {"error": "图未加载，请先运行 scan.py"}
    return state.graph.stats()


@app.on_event("startup")
def on_startup():
    """启动时自动从 SQLite 加载图"""
    state = AppState.get()
    state.refresh_graph_if_needed(force=True)
    if state.graph is not None:
        print(f"[启动] 从 {state.db_path} 加载血缘图...")
        stats = state.graph.stats()
        print(f"[启动] 加载完成：{stats['node_count']} 个节点，{stats['edge_count']} 条边")
    else:
        print(f"[启动] 未找到 {state.db_path}，请先运行: python scan.py")
