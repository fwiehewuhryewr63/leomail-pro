"""
Export / Import router - full data portability.
GET  /api/export  -> download JSON with all accounts, proxies, farms, settings
POST /api/import  -> restore from uploaded JSON
"""
from fastapi import APIRouter, Depends, UploadFile, File
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime
import json

from ..database import get_db
from ..models import Account, Proxy, Farm, farm_accounts

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/")
def export_all(db: Session = Depends(get_db)):
    """Export all data as JSON."""
    accounts = db.query(Account).all()
    proxies = db.query(Proxy).all()
    farms = db.query(Farm).all()

    # Build farm -> account mapping
    farm_data = []
    for farm in farms:
        farm_accs = [a.email for a in farm.accounts] if farm.accounts else []
        farm_data.append({
            "name": farm.name,
            "description": farm.description,
            "account_emails": farm_accs,
        })

    # Export proxies
    proxy_data = []
    for p in proxies:
        proxy_data.append({
            "host": p.host,
            "port": p.port,
            "username": p.username,
            "password": p.password,
            "proxy_type": p.proxy_type,
            "geo": p.geo,
            "status": p.status,
            "use_gmail": p.use_gmail,
            "use_yahoo": p.use_yahoo,
            "use_aol": p.use_aol,
            "use_outlook": p.use_outlook,
            "use_hotmail": p.use_hotmail,
            "use_protonmail": getattr(p, 'use_protonmail', 0),
            "use_tuta": getattr(p, 'use_tuta', 0),
        })

    data = {
        "version": "leomail-export-v1",
        "exported_at": datetime.utcnow().isoformat(),
        "accounts": [a.to_export() for a in accounts],
        "proxies": proxy_data,
        "farms": farm_data,
        "stats": {
            "total_accounts": len(accounts),
            "total_proxies": len(proxies),
            "total_farms": len(farms),
        }
    }
    return data


@router.post("/import")
async def import_data(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Import data from JSON file."""
    try:
        content = await file.read()
        data = json.loads(content)
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"Invalid JSON: {str(e)}"})

    if data.get("version") != "leomail-export-v1":
        return JSONResponse(status_code=400, content={"error": "Unknown export format"})

    imported = {"accounts": 0, "proxies": 0, "farms": 0, "skipped": 0}

    # Import proxies
    for p in data.get("proxies", []):
        existing = db.query(Proxy).filter(Proxy.host == p["host"], Proxy.port == p["port"]).first()
        if existing:
            imported["skipped"] += 1
            continue
        proxy = Proxy(
            host=p["host"], port=p["port"],
            username=p.get("username"), password=p.get("password"),
            proxy_type=p.get("proxy_type", "http"),
            geo=p.get("geo"),
            status=p.get("status", "active"),
            use_gmail=p.get("use_gmail", p.get("use_G", 0)),
            use_yahoo=p.get("use_yahoo", p.get("use_YA", 0)),
            use_aol=p.get("use_aol", 0),
            use_outlook=p.get("use_outlook", p.get("use_OH", 0)),
            use_hotmail=p.get("use_hotmail", 0),
            use_protonmail=p.get("use_protonmail", p.get("use_PT", 0)),
            use_tuta=p.get("use_tuta", p.get("use_TT", 0)),
        )
        db.add(proxy)
        imported["proxies"] += 1

    db.flush()

    # Import accounts
    for a in data.get("accounts", []):
        existing = db.query(Account).filter(Account.email == a["email"]).first()
        if existing:
            imported["skipped"] += 1
            continue
        account = Account(
            email=a["email"], password=a["password"],
            provider=a.get("provider", "outlook"),
            first_name=a.get("first_name"), last_name=a.get("last_name"),
            gender=a.get("gender"), geo=a.get("geo"),
            language=a.get("language"),
            birth_ip=a.get("birth_ip"), user_agent=a.get("user_agent"),
            warmup_day=a.get("warmup_day", 0),
            status=a.get("status", "new"),
            health_score=a.get("health_score", 100),
            metadata_blob={
                "cookies": a.get("cookies", []),
                "fingerprint": a.get("fingerprint", {}),
            }
        )
        if a.get("birthday"):
            try:
                account.birthday = datetime.fromisoformat(a["birthday"])
            except (ValueError, TypeError):
                pass
        db.add(account)
        imported["accounts"] += 1

    db.flush()

    # Import farms + link accounts
    for f in data.get("farms", []):
        existing = db.query(Farm).filter(Farm.name == f["name"]).first()
        if existing:
            farm = existing
        else:
            farm = Farm(name=f["name"], description=f.get("description"))
            db.add(farm)
            db.flush()
            imported["farms"] += 1

        # Link accounts by email
        for email in f.get("account_emails", []):
            acc = db.query(Account).filter(Account.email == email).first()
            if acc and acc not in farm.accounts:
                farm.accounts.append(acc)

    db.commit()
    return {"ok": True, "imported": imported}
