"""Opt-in, disposable PostgreSQL databases; never use DATABASE_URL as a fallback."""

import asyncio
import logging
import os
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def cooking_db(monkeypatch):
    admin_url = os.getenv("INFERENCE_TEST_ADMIN_URL")
    if not admin_url:
        pytest.skip(
            "BLOCKED: set INFERENCE_TEST_ADMIN_URL for a disposable local PostgreSQL cluster"
        )
    url = make_url(admin_url)
    if url.host not in {"127.0.0.1", "localhost"} or url.database != "postgres":
        pytest.fail("Test admin URL must target a local postgres maintenance database")
    name = "inference_test_" + uuid4().hex
    # Only this freshly created database is ever dropped; no existing database is reset.
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                sql.Identifier(name)
            )
        )
    test_url = url.set(database=name)
    engine = None
    try:
        with psycopg.connect(
            test_url.render_as_string(hide_password=False), autocommit=True
        ) as conn:
            conn.execute(Path("scripts/scripts.sql").read_text(), prepare=False)
        engine = create_async_engine(test_url.set(drivername="postgresql+asyncpg"))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setenv(
            "DATABASE_URL",
            test_url.set(drivername="postgresql+asyncpg").render_as_string(
                hide_password=False
            ),
        )
        monkeypatch.setenv("ALLOWED_DEMO_USERS", "synthetic-test-user")
        import insights.insights_service as service

        monkeypatch.setattr(service, "SessionLocal", factory)

        async def rows(query, **params):
            async with factory() as session:
                result = await session.execute(text(query), params)
                return [dict(row) for row in result.mappings()]

        yield SimpleNamespace(
            factory=factory,
            service=service,
            rows=rows,
            user="test_" + uuid4().hex,
            other="test_" + uuid4().hex,
            url=test_url.set(drivername="postgresql+asyncpg").render_as_string(
                hide_password=False
            ),
            logger=logging.getLogger("inference-tests"),
        )
    finally:
        if engine is not None:
            await engine.dispose()
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


@pytest.fixture
async def cooking_mcp(cooking_db, monkeypatch):
    db = cooking_db
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    token = uuid4().hex + uuid4().hex
    env = dict(
        os.environ,
        DATABASE_URL=db.url,
        PORT=str(port),
        ALLOWED_DEMO_USERS=f"{db.user},{db.other}",
        MCP_SERVICE_TOKEN=token,
    )

    env = {
        **os.environ,
        "DATABASE_URL": db.url,
        "PORT": str(port),
        "ALLOWED_DEMO_USERS": f"{db.user},{db.other}",
        "MCP_SERVICE_TOKEN": token,
    }

    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "server.py",
        env=env,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
    )
    try:
        for _ in range(100):
            if process.poll() is not None:
                pytest.fail("Isolated MCP process exited before startup")
            try:
                _, writer = await asyncio.open_connection("127.0.0.1", port)
                writer.close()
                await writer.wait_closed()
                break
            except OSError:
                await asyncio.sleep(0.1)
        else:
            pytest.fail("Isolated MCP startup exceeded 10 seconds")
        import client.mcp_client as bridge

        monkeypatch.setattr(bridge, "MCP_URL", f"http://127.0.0.1:{port}/mcp")
        monkeypatch.setattr(bridge, "MCP_SERVICE_TOKEN", token)
        yield SimpleNamespace(db=db, url=bridge.MCP_URL, token=token, bridge=bridge)
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
