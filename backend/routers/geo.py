"""
Leomail v2.1 - Geo API Router
Serves country/language data to frontend
"""
from fastapi import APIRouter
from ..data.geo_data import get_countries_for_api, get_languages_for_api, SIMSMS_SERVICES

router = APIRouter(prefix="/api/geo", tags=["geo"])


@router.get("/countries")
async def get_countries():
    return get_countries_for_api()


@router.get("/languages")
async def get_languages():
    return get_languages_for_api()


@router.get("/providers")
async def get_providers():
    """Email providers with SimSMS service codes."""
    return [
        {"id": "gmail", "name": "Gmail", "simsms_service": "go", "difficulty": 5,
         "mobile_only": True, "proxy_type": "mobile",
         "description": "Mobile proxy required. Android emulation."},
        {"id": "outlook", "name": "Outlook", "simsms_service": "mm", "difficulty": 2,
         "mobile_only": False, "proxy_type": "any",
         "description": "Any proxy. Desktop emulation."},
        {"id": "hotmail", "name": "Hotmail", "simsms_service": "mm", "difficulty": 2,
         "mobile_only": False, "proxy_type": "any",
         "description": "Microsoft account, same as Outlook."},
        {"id": "yahoo", "name": "Yahoo", "simsms_service": "mb", "difficulty": 3,
         "mobile_only": False, "proxy_type": "residential",
         "description": "Residential/mobile proxy recommended."},
        {"id": "aol", "name": "AOL", "simsms_service": "pm", "difficulty": 1,
         "mobile_only": False, "proxy_type": "any",
         "description": "Easiest provider. Any proxy."},
        {"id": "webde", "name": "Web.de", "simsms_service": "ot", "difficulty": 2,
         "mobile_only": False, "proxy_type": "residential",
         "description": "German provider. SMS verification. Residential proxy."},
    ]
