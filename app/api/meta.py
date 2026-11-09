from fastapi import APIRouter

from app import geo, taxonomy

router = APIRouter(tags=["reference"])


@router.get("/taxonomy")
def get_taxonomy():
    return {"categories": taxonomy.categories()}


@router.get("/departments")
def get_departments():
    return {"departments": taxonomy.departments()}


@router.get("/wards")
def get_wards():
    return geo.load_wards()
