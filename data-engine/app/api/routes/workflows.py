from fastapi import APIRouter

from app.workflows.catalog import WORKFLOW_CATALOG

router = APIRouter()


@router.get("")
def workflows() -> dict:
    return {"workflows": WORKFLOW_CATALOG}

