from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import RecipientDatabase
from ..schemas import DatabaseUpload
from loguru import logger
from pathlib import Path
import re
import json

router = APIRouter(prefix="/api/databases", tags=["databases"])

DATABASES_DIR = Path("user_data/databases")


def _validate_email(email: str) -> bool:
    return bool(re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email.strip()))


@router.get("/")
async def list_databases(db: Session = Depends(get_db)):
    dbs = db.query(RecipientDatabase).order_by(RecipientDatabase.created_at.desc()).all()
    result = []
    for d in dbs:
        # Detect format from file
        has_names = False
        try:
            fp = Path(d.file_path)
            if fp.exists() and fp.suffix == '.json':
                sample = json.loads(fp.read_text(encoding='utf-8'))
                if sample and isinstance(sample, list) and sample[0].get('first_name'):
                    has_names = True
        except Exception:
            pass

        result.append({
            "id": d.id,
            "name": d.name,
            "total_count": d.total_count,
            "used_count": d.used_count,
            "invalid_count": d.invalid_count,
            "remaining": d.total_count - d.used_count,
            "with_name": has_names,
            "file_path": d.file_path,
            "created_at": d.created_at.isoformat() if d.created_at else None
        })
    return result


@router.post("/upload")
async def upload_database(req: DatabaseUpload, db: Session = Depends(get_db)):
    """
    Upload recipient database with 3 supported formats:
    1. email only           → {{EMAILNAME}}
    2. email,FirstName      → {{EMAILNAME}},{{FIRSTNAME}}
    3. email,First,Last     → {{EMAILNAME}},{{FIRSTNAME}},{{LASTNAME}}
    """
    DATABASES_DIR.mkdir(parents=True, exist_ok=True)

    valid_entries = []
    invalid_count = 0
    seen = set()

    for entry in req.entries:
        email = entry.email.strip().lower()
        if email and email not in seen:
            seen.add(email)
            if _validate_email(email):
                valid_entries.append({
                    "email": email,
                    "first_name": entry.first_name.strip() if entry.first_name else "",
                    "last_name": entry.last_name.strip() if entry.last_name else "",
                })
            else:
                invalid_count += 1

    if not valid_entries:
        return {"error": "No valid emails found"}

    # Save as JSON (preserves names)
    safe_name = re.sub(r'[^\w\-.]', '_', req.name)
    file_path = DATABASES_DIR / f"{safe_name}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(valid_entries, f, ensure_ascii=False, indent=2)

    # Save to DB
    rec_db = RecipientDatabase(
        name=req.name,
        file_path=str(file_path),
        total_count=len(valid_entries),
        invalid_count=invalid_count
    )
    db.add(rec_db)
    db.commit()
    db.refresh(rec_db)

    # Determine format type
    has_first = any(e['first_name'] for e in valid_entries)
    has_last = any(e['last_name'] for e in valid_entries)
    fmt = "email"
    if has_first and has_last:
        fmt = "email,firstname,lastname"
    elif has_first:
        fmt = "email,firstname"

    logger.info(f"Database '{req.name}' uploaded: {len(valid_entries)} entries (format: {fmt})")

    return {
        "id": rec_db.id,
        "name": rec_db.name,
        "total_count": len(valid_entries),
        "invalid_count": invalid_count,
        "format": fmt,
        "status": "uploaded"
    }


@router.post("/upload-file")
async def upload_database_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload .txt file with recipients (one per line).
    
    Supported formats:
    1. email only           (one email per line)
    2. email,FirstName      (comma separated)
    3. email,First,Last     (comma separated)
    """
    DATABASES_DIR.mkdir(parents=True, exist_ok=True)

    try:
        content = await file.read()
        text = content.decode("utf-8", errors="ignore")
    except Exception as e:
        return {"error": f"File read error: {e}"}

    valid_entries = []
    invalid_count = 0
    seen = set()

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        parts = [p.strip() for p in line.split(",")]
        email = parts[0].lower()

        if not email or email in seen:
            continue
        seen.add(email)

        if _validate_email(email):
            first_name = parts[1] if len(parts) >= 2 else ""
            last_name = parts[2] if len(parts) >= 3 else ""
            valid_entries.append({
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            })
        else:
            invalid_count += 1

    if not valid_entries:
        return {"error": "No valid emails found in file"}

    # Save as JSON
    db_name = file.filename.rsplit(".", 1)[0] if file.filename else "imported"
    safe_name = re.sub(r'[^\w\-.]', '_', db_name)
    file_path = DATABASES_DIR / f"{safe_name}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(valid_entries, f, ensure_ascii=False, indent=2)

    # Detect format
    has_first = any(e['first_name'] for e in valid_entries)
    has_last = any(e['last_name'] for e in valid_entries)
    if has_first and has_last:
        fmt = "email+name+lastname"
        fmt_icon = "👥"
    elif has_first:
        fmt = "email+name"
        fmt_icon = "👤"
    else:
        fmt = "email"
        fmt_icon = "📧"

    # Save to DB
    rec_db = RecipientDatabase(
        name=db_name,
        file_path=str(file_path),
        total_count=len(valid_entries),
        invalid_count=invalid_count,
        with_name=has_first,
    )
    db.add(rec_db)
    db.commit()
    db.refresh(rec_db)

    logger.info(f"Database '{db_name}' uploaded from file: {len(valid_entries)} entries ({fmt})")

    return {
        "id": rec_db.id,
        "name": db_name,
        "total_count": len(valid_entries),
        "invalid_count": invalid_count,
        "format": fmt,
        "format_icon": fmt_icon,
        "status": "uploaded",
    }

@router.get("/{db_id}")
async def get_database(db_id: int, db: Session = Depends(get_db)):
    rec = db.query(RecipientDatabase).filter(RecipientDatabase.id == db_id).first()
    if not rec:
        return {"error": "Database not found"}

    preview = []
    try:
        fp = Path(rec.file_path)
        if fp.exists():
            if fp.suffix == '.json':
                entries = json.loads(fp.read_text(encoding='utf-8'))
                for entry in entries:
                    parts = [entry['email']]
                    if entry.get('first_name'):
                        parts.append(entry['first_name'])
                    if entry.get('last_name'):
                        parts.append(entry['last_name'])
                    preview.append(','.join(parts))
            else:
                # Legacy .txt format
                with open(fp, "r", encoding="utf-8") as f:
                    for i, line in enumerate(f):
                        if i >= 50:
                            break
                        preview.append(line.strip())
    except Exception:
        pass

    return {
        "id": rec.id,
        "name": rec.name,
        "total_count": rec.total_count,
        "used_count": rec.used_count,
        "remaining": rec.total_count - rec.used_count,
        "preview": preview
    }


@router.get("/{db_id}/entries")
async def get_database_entries(db_id: int, offset: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Get entries with full data (email, first_name, last_name) for template rendering."""
    rec = db.query(RecipientDatabase).filter(RecipientDatabase.id == db_id).first()
    if not rec:
        return {"error": "Database not found"}

    entries = []
    try:
        fp = Path(rec.file_path)
        if fp.exists() and fp.suffix == '.json':
            all_entries = json.loads(fp.read_text(encoding='utf-8'))
            entries = all_entries[offset:offset + limit]
        elif fp.exists():
            # Legacy .txt
            with open(fp, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for line in lines[offset:offset + limit]:
                entries.append({"email": line.strip(), "first_name": "", "last_name": ""})
    except Exception:
        pass

    return {"entries": entries, "total": rec.total_count}


@router.post("/batch-delete")
async def batch_delete_databases(req: dict, db: Session = Depends(get_db)):
    """Delete multiple databases by IDs."""
    ids = req.get("ids", [])
    if not ids:
        return {"deleted": 0}
    recs = db.query(RecipientDatabase).filter(RecipientDatabase.id.in_(ids)).all()
    for r in recs:
        try:
            Path(r.file_path).unlink(missing_ok=True)
        except Exception:
            pass
        db.delete(r)
    db.commit()
    return {"deleted": len(recs)}


@router.post("/{db_id}/reset-progress")
async def reset_progress(db_id: int, db: Session = Depends(get_db)):
    """Reset used_count and clear MailingStats for this database's recipients."""
    from ..models import MailingStats

    rec = db.query(RecipientDatabase).filter(RecipientDatabase.id == db_id).first()
    if not rec:
        return {"error": "Database not found"}

    # Load emails from this database
    emails_to_reset = set()
    try:
        fp = Path(rec.file_path)
        if fp.exists() and fp.suffix == '.json':
            entries = json.loads(fp.read_text(encoding='utf-8'))
            for entry in entries:
                email = entry.get("email", "").strip().lower()
                if email:
                    emails_to_reset.add(email)
        elif fp.exists():
            with open(fp, "r", encoding="utf-8") as f:
                for line in f:
                    email = line.strip().split(",")[0].strip().lower()
                    if "@" in email:
                        emails_to_reset.add(email)
    except Exception as e:
        logger.error(f"Error reading database file: {e}")

    # Delete MailingStats entries for these emails
    cleared = 0
    if emails_to_reset:
        cleared = db.query(MailingStats).filter(
            MailingStats.recipient_email.in_(emails_to_reset),
            MailingStats.status == "sent",
        ).delete(synchronize_session=False)

    # Reset used_count
    old_used = rec.used_count
    rec.used_count = 0
    db.commit()

    logger.info(f"Reset progress for '{rec.name}': used_count {old_used} → 0, cleared {cleared} stats")
    return {
        "ok": True,
        "database": rec.name,
        "cleared_stats": cleared,
        "old_used_count": old_used,
    }

@router.delete("/{db_id}")
async def delete_database(db_id: int, db: Session = Depends(get_db)):
    rec = db.query(RecipientDatabase).filter(RecipientDatabase.id == db_id).first()
    if not rec:
        return {"error": "Database not found"}

    try:
        Path(rec.file_path).unlink(missing_ok=True)
    except Exception:
        pass

    db.delete(rec)
    db.commit()
    return {"status": "deleted"}
