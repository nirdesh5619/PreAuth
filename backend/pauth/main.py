"""FastAPI entrypoint: CORS, SQLite, compiled LangGraph, API router."""

from contextlib import asynccontextmanager

import aiosqlite
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from pauth.api import router
from pauth.config import settings
from pauth.db import init_db
from pauth.graph.builder import build_graph


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create local data dirs, open the checkpoint DB, and compile the graph.

    The checkpointer is a separate SQLite file from the app DB so LangGraph
    HITL interrupts survive a page refresh without locking case tables.
    """
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    await init_db()
    conn = await aiosqlite.connect(settings.checkpoint_db_path)
    conn.row_factory = aiosqlite.Row
    checkpointer = AsyncSqliteSaver(conn)
    await checkpointer.setup()
    app.state.db_conn = conn
    app.state.graph = build_graph(checkpointer)
    yield
    await conn.close()


app = FastAPI(title="Prior Auth Agent", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
