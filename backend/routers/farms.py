from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Farm, Account, farm_accounts
from ..schemas import FarmCreate, FarmMerge, FarmSplit
from loguru import logger
from fastapi.responses import StreamingResponse
import json, zipfile, io, datetime

router = APIRouter(prefix="/api/farms", tags=["farms"])


@router.get("/")
async def list_farms(db: Session = Depends(get_db)):
    farms = db.query(Farm).all()
    result = []
    for farm in farms:
        accounts = farm.accounts
        providers = {}
        statuses = {"new": 0, "phase_1": 0, "phase_2": 0, "phase_3": 0, "phase_4": 0, "phase_5": 0, "warmed": 0, "sending": 0, "dead": 0, "banned": 0}
        for acc in accounts:
            providers[acc.provider] = providers.get(acc.provider, 0) + 1
            if acc.status in statuses:
                statuses[acc.status] += 1

        total = len(accounts)
        warmed = statuses["warmed"] + statuses["sending"]
        progress = int((warmed / total) * 100) if total > 0 else 0

        result.append({
            "id": farm.id,
            "name": farm.name,
            "description": farm.description,
            "accounts_count": total,
            "providers": providers,
            "statuses": statuses,
            "warmup_progress": progress,
            "created_at": farm.created_at.isoformat() if farm.created_at else None
        })
    return result


@router.post("/")
async def create_farm(req: FarmCreate, db: Session = Depends(get_db)):
    farm = Farm(name=req.name, description=req.description)
    db.add(farm)
    db.commit()
    db.refresh(farm)
    return {"id": farm.id, "name": farm.name, "status": "created"}


@router.get("/{farm_id}")
async def get_farm(farm_id: int, db: Session = Depends(get_db)):
    farm = db.query(Farm).filter(Farm.id == farm_id).first()
    if not farm:
        return {"error": "Farm not found"}
    accounts = [
        {
            "id": a.id,
            "email": a.email,
            "provider": a.provider,
            "status": a.status,
            "warmup_day": a.warmup_day,
            "health_score": a.health_score,
            "gender": a.gender,
            "geo": a.geo,
            "proxy": a.proxy.to_string() if a.proxy else None,
        }
        for a in farm.accounts
    ]
    return {
        "id": farm.id,
        "name": farm.name,
        "description": farm.description,
        "accounts": accounts
    }


@router.post("/batch-delete")
async def batch_delete_farms(req: dict, db: Session = Depends(get_db)):
    """Delete multiple farms by IDs."""
    ids = req.get("ids", [])
    if not ids:
        return {"deleted": 0}
    count = db.query(Farm).filter(Farm.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    return {"deleted": count}

@router.delete("/{farm_id}")
async def delete_farm(farm_id: int, db: Session = Depends(get_db)):
    farm = db.query(Farm).filter(Farm.id == farm_id).first()
    if not farm:
        return {"error": "Farm not found"}
    db.delete(farm)
    db.commit()
    return {"status": "deleted", "id": farm_id}


@router.post("/merge")
async def merge_farms(req: FarmMerge, db: Session = Depends(get_db)):
    """Merge multiple farms into one new farm."""
    new_farm = Farm(name=req.target_name)
    db.add(new_farm)
    db.flush()

    merged_count = 0
    for source_id in req.source_farm_ids:
        source = db.query(Farm).filter(Farm.id == source_id).first()
        if source:
            for acc in source.accounts:
                if acc not in new_farm.accounts:
                    new_farm.accounts.append(acc)
                    merged_count += 1

    db.commit()
    return {
        "status": "merged",
        "new_farm_id": new_farm.id,
        "accounts_merged": merged_count
    }


@router.post("/split")
async def split_farm(req: FarmSplit, db: Session = Depends(get_db)):
    """Split a farm by provider, geo, or status."""
    farm = db.query(Farm).filter(Farm.id == req.farm_id).first()
    if not farm:
        return {"error": "Farm not found"}

    groups = {}
    for acc in farm.accounts:
        if req.split_by == "provider":
            key = acc.provider or "unknown"
        elif req.split_by == "geo":
            key = acc.geo or "unknown"
        elif req.split_by == "status":
            key = acc.status or "unknown"
        else:
            key = "all"
        groups.setdefault(key, []).append(acc)

    new_farms = []
    for key, accounts in groups.items():
        nf = Farm(name=f"{req.new_farm_name_prefix}_{key}")
        db.add(nf)
        db.flush()
        for acc in accounts:
            nf.accounts.append(acc)
        new_farms.append({"id": nf.id, "name": nf.name, "count": len(accounts)})

    db.commit()
    return {"status": "split", "new_farms": new_farms}


@router.get("/{farm_id}/export")
async def export_farm(farm_id: int, db: Session = Depends(get_db)):
    """Export farm as ZIP archive with accounts."""
    farm = db.query(Farm).filter(Farm.id == farm_id).first()
    if not farm:
        return {"error": "Farm not found"}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Farm metadata
        farm_info = {
            "farm_name": farm.name,
            "description": farm.description or "",
            "exported_at": datetime.datetime.utcnow().isoformat(),
            "total_accounts": len(farm.accounts),
        }
        zf.writestr("farm_info.json", json.dumps(farm_info, indent=2, ensure_ascii=False))

        # Each account as separate JSON
        for i, acc in enumerate(farm.accounts):
            acc_data = {
                "id": acc.id,
                "email": acc.email,
                "password": acc.password,
                "provider": acc.provider,
                "status": acc.status,
                "warmup_day": acc.warmup_day,
                "health_score": acc.health_score,
                "gender": acc.gender,
                "geo": acc.geo,
                "first_name": acc.first_name,
                "last_name": acc.last_name,
                "recovery_email": acc.recovery_email,
                "recovery_phone": acc.recovery_phone,
                "created_at": acc.created_at.isoformat() if acc.created_at else None,
            }
            safe_email = acc.email.replace("@", "_at_").replace(".", "_")
            zf.writestr(f"accounts/{safe_email}.json", json.dumps(acc_data, indent=2, ensure_ascii=False))

    buf.seek(0)
    safe_name = farm.name.replace(" ", "_").replace("/", "_")
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="farm_{safe_name}.zip"'}
    )
