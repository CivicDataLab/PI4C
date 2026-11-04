from fastapi import APIRouter, Depends

from app import geo, taxonomy
from app.auth import require_scope

router = APIRouter(tags=["reference"])


@router.get("/taxonomy")
def get_taxonomy(_=Depends(require_scope("read"))):
    return {"categories": taxonomy.categories()}


@router.get("/departments")
def get_departments(_=Depends(require_scope("read"))):
    return {"departments": taxonomy.departments()}


@router.get("/wards")
def get_wards(_=Depends(require_scope("read"))):
    return geo.load_wards()
