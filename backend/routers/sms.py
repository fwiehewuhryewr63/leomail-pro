"""
Leomail v2.2 - SMS API Router
Pricing, country availability, and SMS service endpoints.
"""
from fastapi import APIRouter
from ..config import load_config
from ..services.simsms_provider import SimSmsProvider

router = APIRouter(prefix="/api/sms", tags=["sms"])


def _get_provider():
    config = load_config()
    api_key = config.get("api_keys", {}).get("simsms", "")
    return SimSmsProvider(api_key)


@router.get("/balance")
async def sms_balance():
    """Get SMS provider balance."""
    p = _get_provider()
    return {"balance": p.get_balance(), "currency": "RUB"}


@router.get("/prices")
async def sms_prices(service: str = "gmail", country: str = "ru"):
    """Get price + availability for service+country."""
    p = _get_provider()
    return p.get_prices(service, country)


@router.get("/countries")
async def sms_countries(service: str = "gmail"):
    """Get available countries for a service with prices."""
    p = _get_provider()
    return p.get_available_countries(service)
