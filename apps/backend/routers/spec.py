"""Routes for assignment specs and requirement tracking.

Stub endpoints for importing a :class:`models.Spec` and managing the
:class:`models.RequirementItem` checklist parsed from it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session as DBSession

from db import get_session

router = APIRouter(prefix="/spec", tags=["spec"])


@router.post("/import")
async def import_spec(db: DBSession = Depends(get_session)) -> dict:
    """Import a spec (PDF/text) and parse requirements. Stub."""

    return {}


@router.get("/{spec_id}/requirements")
async def list_requirements(
    spec_id: int, db: DBSession = Depends(get_session)
) -> list[dict]:
    """List tracked requirement items for a spec. Stub."""

    return []


@router.put("/requirements/{item_id}")
async def update_requirement(
    item_id: int, db: DBSession = Depends(get_session)
) -> dict:
    """Toggle or edit a requirement item. Stub."""

    return {}
