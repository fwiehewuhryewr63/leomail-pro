from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Farm, Account, farm_accounts
from ..schemas import FarmCreate, FarmMerge, FarmSplit
from loguru import logger
from fastapi.responses import StreamingResponse
import json, zipfile, io, datetime, random
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/farms", tags=["farms"])


@router.get("/")
async def list_farms(db: Session = Depends(get_db)):
    farms = db.query(Farm).all()
    result = []
    for farm in farms:
        accounts = farm.accounts
        providers = {}
        geos = {}
        statuses = {"new": 0, "phase_1": 0, "phase_2": 0, "phase_3": 0, "phase_4": 0, "phase_5": 0, "warmed": 0, "sending": 0, "dead": 0, "banned": 0}
        for acc in accounts:
            providers[acc.provider] = providers.get(acc.provider, 0) + 1
            if acc.geo:
                geos[acc.geo] = geos.get(acc.geo, 0) + 1
            if acc.status in statuses:
                statuses[acc.status] += 1

        total = len(accounts)
        warmed = statuses["warmed"] + statuses["sending"]
        progress = int((warmed / total) * 100) if total > 0 else 0

        result.append({
            "id": farm.id,
            "name": farm.name,
            "description": farm.description,
            "account_count": total,
            "accounts_count": total,  # backward compat
            "providers": providers,
            "geos": geos,
            "gender": "female",  # always female
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


# ─── Provider detection from email domain ───
DOMAIN_PROVIDER = {
    "gmail.com": "gmail", "googlemail.com": "gmail",
    "yahoo.com": "yahoo", "yahoo.co.uk": "yahoo", "yahoo.co.jp": "yahoo",
    "aol.com": "aol",
    "outlook.com": "outlook", "outlook.de": "outlook", "outlook.fr": "outlook",
    "hotmail.com": "hotmail", "hotmail.co.uk": "hotmail", "hotmail.fr": "hotmail",
    "live.com": "outlook", "msn.com": "outlook",
}


def _detect_provider(email: str) -> str:
    """Detect provider from email domain."""
    domain = email.split("@")[-1].lower()
    if domain in DOMAIN_PROVIDER:
        return DOMAIN_PROVIDER[domain]
    # Fallback: check partial matches
    for pattern, prov in DOMAIN_PROVIDER.items():
        if domain.endswith(pattern.split(".")[-1]) and pattern.split(".")[0] in domain:
            return prov
    return "unknown"


def _extract_name(email: str) -> tuple[str, str]:
    """Try to extract first/last name from email prefix."""
    prefix = email.split("@")[0]
    # Remove digits and common separators
    cleaned = ""
    for c in prefix:
        if c.isalpha():
            cleaned += c
        elif c in "._-":
            cleaned += " "
    parts = cleaned.strip().split()
    if len(parts) >= 2:
        return parts[0].capitalize(), parts[1].capitalize()
    elif len(parts) == 1:
        return parts[0].capitalize(), ""
    return "", ""


class AccountImportRequest(BaseModel):
    lines: list[str]


@router.post("/{farm_id}/import-accounts")
async def import_accounts(farm_id: int, req: AccountImportRequest, db: Session = Depends(get_db)):
    """Import accounts from text lines: email:pass or email:pass:recovery:recpass."""
    farm = db.query(Farm).filter(Farm.id == farm_id).first()
    if not farm:
        return {"error": "Farm not found"}

    imported = 0
    skipped = 0
    providers = {}

    for line in req.lines:
        line = line.strip()
        if not line or "@" not in line:
            skipped += 1
            continue

        parts = line.split(":")
        if len(parts) < 2:
            skipped += 1
            continue

        email = parts[0].strip()
        password = parts[1].strip()
        recovery_email = parts[2].strip() if len(parts) > 2 else None
        recovery_pass = parts[3].strip() if len(parts) > 3 else None

        # Skip if already exists
        existing = db.query(Account).filter(Account.email == email).first()
        if existing:
            # If exists but not in this farm, add to farm
            if existing not in farm.accounts:
                farm.accounts.append(existing)
                imported += 1
                p = existing.provider or "unknown"
                providers[p] = providers.get(p, 0) + 1
            else:
                skipped += 1
            continue

        provider = _detect_provider(email)
        first_name, last_name = _extract_name(email)

        # Generate random birthday (18-35 years old)
        year = random.randint(1990, 2006)
        month = random.randint(1, 12)
        day = random.randint(1, 28)
        birthday = datetime.datetime(year, month, day)

        gender = random.choice(["male", "female"])

        account = Account(
            email=email,
            password=password,
            provider=provider,
            status="new",
            first_name=first_name,
            last_name=last_name,
            gender=gender,
            birthday=birthday,
            recovery_email=recovery_email,
            geo="US",
            language="en",
        )
        # Store recovery password in metadata
        if recovery_pass:
            account.metadata_blob = {"recovery_pass": recovery_pass}

        db.add(account)
        db.flush()
        farm.accounts.append(account)
        imported += 1
        providers[provider] = providers.get(provider, 0) + 1

    db.commit()
    logger.info(f"Imported {imported} accounts into farm '{farm.name}' (skipped {skipped})")
    return {
        "imported": imported,
        "skipped": skipped,
        "providers": providers,
    }

