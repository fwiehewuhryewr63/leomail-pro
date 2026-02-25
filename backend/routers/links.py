from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import LinkDatabase
from ..config import CONFIG_DIR
from loguru import logger
import shutil
import os

router = APIRouter(prefix="/api/links", tags=["links"])

LINKS_DIR = CONFIG_DIR / "links"
LINKS_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/")
async def list_link_databases(db: Session = Depends(get_db)):
    """List all link packs."""
    dbs = db.query(LinkDatabase).order_by(LinkDatabase.created_at.desc()).all()
    return [{
        "id": d.id,
        "name": d.name,
        "total_count": d.total_count,
        "niche": d.niche or "",
        "created_at": d.created_at.isoformat()
    } for d in dbs]


@router.post("/upload")
async def upload_link_database(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload a text file with links (one per line)."""
    try:
        content = await file.read()
        text = content.decode("utf-8", errors="ignore")
        
        # Parse and count
        lines = [l.strip() for l in text.split("\n") if l.strip().startswith("http")]
        count = len(lines)
        
        if count == 0:
            return {"error": "No valid links found (must start with http/https)"}

        # Save file
        filename = f"{int(os.path.getctime(os.path.join('.')) if os.path.exists('.') else 0)}_{file.filename}"
        file_path = LINKS_DIR / filename
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
            
        # Create DB entry
        link_db = LinkDatabase(
            name=file.filename,
            file_path=str(file_path.relative_to(CONFIG_DIR)),
            total_count=count
        )
        db.add(link_db)
        db.commit()
        
        return {"status": "ok", "count": count, "name": file.filename}
        
    except Exception as e:
        logger.error(f"Link upload error: {e}")
        return {"error": str(e)}


from pydantic import BaseModel


class LinkTextUpload(BaseModel):
    name: str = ""
    text: str
    niche: str = ""


@router.post("/upload-text")
async def upload_links_text(req: LinkTextUpload, db: Session = Depends(get_db)):
    """Upload links from pasted text (one link per line)."""
    lines = [l.strip() for l in req.text.split("\n") if l.strip().startswith("http")]
    if not lines:
        return {"error": "No valid links found (must start with http/https)"}

    pack_name = req.name.strip() or f"paste_{len(lines)}_links"
    import time
    filename = f"{int(time.time())}_{pack_name}.txt"
    file_path = LINKS_DIR / filename

    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    link_db = LinkDatabase(
        name=pack_name,
        file_path=str(file_path.relative_to(CONFIG_DIR)),
        total_count=len(lines),
        niche=req.niche or None,
    )
    db.add(link_db)
    db.commit()
    return {"status": "ok", "count": len(lines), "name": pack_name}

@router.get("/{pack_id}/preview")
async def preview_link_pack(pack_id: int, db: Session = Depends(get_db)):
    """Return all links from a pack."""
    pack = db.query(LinkDatabase).filter(LinkDatabase.id == pack_id).first()
    if not pack:
        return {"error": "Pack not found", "links": []}
    full_path = CONFIG_DIR / pack.file_path
    if not full_path.exists():
        return {"error": "File not found", "links": [], "name": pack.name}
    lines = []
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(line)
    except Exception:
        pass
    return {"name": pack.name, "total": pack.total_count, "links": lines}


@router.post("/batch-delete")
async def batch_delete_links(req: dict, db: Session = Depends(get_db)):
    """Delete multiple link packs by IDs."""
    ids = req.get("ids", [])
    if not ids:
        return {"deleted": 0}
    packs = db.query(LinkDatabase).filter(LinkDatabase.id.in_(ids)).all()
    for p in packs:
        try:
            full_path = CONFIG_DIR / p.file_path
            if full_path.exists():
                os.remove(full_path)
        except Exception:
            pass
        db.delete(p)
    db.commit()
    return {"deleted": len(packs)}


@router.delete("/{id}")
async def delete_link_database(id: int, db: Session = Depends(get_db)):
    link_db = db.query(LinkDatabase).filter(LinkDatabase.id == id).first()
    if not link_db:
        return {"error": "Not found"}
        
    # Try delete file
    try:
        full_path = CONFIG_DIR / link_db.file_path
        if full_path.exists():
            os.remove(full_path)
    except Exception:
        pass
        
    db.delete(link_db)
    db.commit()
    return {"status": "deleted"}
