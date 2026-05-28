"""Routes for notebook cells.

Stub endpoints for creating, updating, and running :class:`models.Cell`
records. Execution will be delegated to
:class:`services.psirver_client.PsirverClient` once implemented.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session as DBSession

from db import get_session

router = APIRouter(prefix="/cells", tags=["cells"])


@router.post("")
async def create_cell(db: DBSession = Depends(get_session)) -> dict:
    """Create a new cell. Stub."""

    return {}


@router.put("/{cell_id}")
async def update_cell(
    cell_id: int, db: DBSession = Depends(get_session)
) -> dict:
    """Update a cell's source or metadata. Stub."""

    return {}


@router.post("/{cell_id}/run")
async def run_cell(cell_id: int, db: DBSession = Depends(get_session)) -> dict:
    """Submit a cell for execution via Psirver. Stub."""

    return {}


@router.delete("/{cell_id}")
async def delete_cell(
    cell_id: int, db: DBSession = Depends(get_session)
) -> dict:
    """Delete a cell. Stub."""

    return {}
