from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..services.sms_provider import GrizzlySMS
from ..services.captcha_provider import CaptchaProvider
import os

router = APIRouter(prefix="/api/services", tags=["services"])

class ServiceTestRequest(BaseModel):
    api_key: str
    service_type: str # "grizzly", "capguru"

@router.post("/test")
async def test_service(request: ServiceTestRequest):
    if request.service_type == "grizzly":
        provider = GrizzlySMS(request.api_key)
        balance = provider.get_balance()
        return {"status": "ok", "message": f"Grizzly SMS connected. Balance: {balance}"}
    
    elif request.service_type == "capguru":
        provider = CaptchaProvider()
        return {"status": "ok", "message": "Cap.guru configured"}
    
    raise HTTPException(status_code=400, detail="Unknown service type")
