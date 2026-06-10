from __future__ import annotations

import typer

from .db import init_db, session_scope
from .service import seed_demo_data

app = typer.Typer(help="Permissioned Agent Memory Gateway utilities.")


@app.command()
def seed() -> None:
    """Initialize tables and seed demo agents/memories."""
    init_db()
    with session_scope() as session:
        seed_demo_data(session)
    typer.echo("Seeded demo data.")


@app.command()
def api(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Run the REST API."""
    import uvicorn

    init_db()
    uvicorn.run("memory_gateway.api.main:app", host=host, port=port, reload=False)


@app.command()
def mcp() -> None:
    """Run the MCP server."""
    from .mcp.server import main

    main()


def run_api() -> None:
    api()


def run_mcp() -> None:
    mcp()


if __name__ == "__main__":
    app()

