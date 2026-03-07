"""
Leomail v3 - Names Router
Upload, list, delete name packs. Get random name from selected packs.
Format: firstname,lastname or firstname lastname per line.
"""
from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session
from ..database import get_db, SessionLocal
from ..models import NamePack
from ..config import load_config, CONFIG_DIR
from loguru import logger
import os, random, shutil

router = APIRouter(prefix="/api/names", tags=["names"])

# Use CONFIG_DIR (absolute path next to EXE) - NOT relative paths!
NAMES_DIR = str(CONFIG_DIR / "names")
os.makedirs(NAMES_DIR, exist_ok=True)

# Built-in GEO name packs directory
BUILTIN_NAMES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "names")

# GEO pack labels â€” maps filename stem to display name
GEO_LABELS = {
    # -- USA --
    "us_names_M_25k": "USA (M)",
    "us_names_F_25k": "USA (F)",
    "us_names_Mix_50k": "USA (Mix)",
    # -- Canada --
    "canada_M_25k": "Canada (M)",
    "canada_F_25k": "Canada (F)",
    "canada_Mix_50k": "Canada (Mix)",
    # -- Brazil --
    "brazil_M_25k": "Brazil (M)",
    "brazil_F_25k": "Brazil (F)",
    "brazil_Mix_50k": "Brazil (Mix)",
    # -- Mexico --
    "mexico_M_25k": "Mexico (M)",
    "mexico_F_25k": "Mexico (F)",
    "mexico_Mix_50k": "Mexico (Mix)",
    # -- Colombia --
    "colombia_M_25k": "Colombia (M)",
    "colombia_F_25k": "Colombia (F)",
    "colombia_Mix_50k": "Colombia (Mix)",
    # -- Argentina --
    "argentina_M_25k": "Argentina (M)",
    "argentina_F_25k": "Argentina (F)",
    "argentina_Mix_50k": "Argentina (Mix)",
    # -- Peru --
    "peru_M_25k": "Peru (M)",
    "peru_F_25k": "Peru (F)",
    "peru_Mix_50k": "Peru (Mix)",
    # -- Venezuela --
    "venezuela_M_25k": "Venezuela (M)",
    "venezuela_F_25k": "Venezuela (F)",
    "venezuela_Mix_50k": "Venezuela (Mix)",
    # -- Chile --
    "chile_M_25k": "Chile (M)",
    "chile_F_25k": "Chile (F)",
    "chile_Mix_50k": "Chile (Mix)",
    # -- Ecuador --
    "ecuador_M_25k": "Ecuador (M)",
    "ecuador_F_25k": "Ecuador (F)",
    "ecuador_Mix_50k": "Ecuador (Mix)",
    # -- Guatemala --
    "guatemala_M_25k": "Guatemala (M)",
    "guatemala_F_25k": "Guatemala (F)",
    "guatemala_Mix_50k": "Guatemala (Mix)",
    # -- Dominican Rep --
    "dominican_M_25k": "Dominican Rep (M)",
    "dominican_F_25k": "Dominican Rep (F)",
    "dominican_Mix_50k": "Dominican Rep (Mix)",
    # -- Honduras --
    "honduras_M_25k": "Honduras (M)",
    "honduras_F_25k": "Honduras (F)",
    "honduras_Mix_50k": "Honduras (Mix)",
    # -- Paraguay --
    "paraguay_M_25k": "Paraguay (M)",
    "paraguay_F_25k": "Paraguay (F)",
    "paraguay_Mix_50k": "Paraguay (Mix)",
    # -- El Salvador --
    "el_salvador_M_25k": "El Salvador (M)",
    "el_salvador_F_25k": "El Salvador (F)",
    "el_salvador_Mix_50k": "El Salvador (Mix)",
    # -- Nicaragua --
    "nicaragua_M_25k": "Nicaragua (M)",
    "nicaragua_F_25k": "Nicaragua (F)",
    "nicaragua_Mix_50k": "Nicaragua (Mix)",
    # -- Costa Rica --
    "costa_rica_M_25k": "Costa Rica (M)",
    "costa_rica_F_25k": "Costa Rica (F)",
    "costa_rica_Mix_50k": "Costa Rica (Mix)",
    # -- Panama --
    "panama_M_25k": "Panama (M)",
    "panama_F_25k": "Panama (F)",
    "panama_Mix_50k": "Panama (Mix)",
    # -- Uruguay --
    "uruguay_M_25k": "Uruguay (M)",
    "uruguay_F_25k": "Uruguay (F)",
    "uruguay_Mix_50k": "Uruguay (Mix)",
    # -- Cuba --
    "cuba_M_25k": "Cuba (M)",
    "cuba_F_25k": "Cuba (F)",
    "cuba_Mix_50k": "Cuba (Mix)",
    # -- Bolivia --
    "bolivia_M_25k": "Bolivia (M)",
    "bolivia_F_25k": "Bolivia (F)",
    "bolivia_Mix_50k": "Bolivia (Mix)",
    # -- Puerto Rico --
    "puerto_rico_M_25k": "Puerto Rico (M)",
    "puerto_rico_F_25k": "Puerto Rico (F)",
    "puerto_rico_Mix_50k": "Puerto Rico (Mix)",
    # -- UK --
    "uk_M_25k": "UK (M)",
    "uk_F_25k": "UK (F)",
    "uk_Mix_50k": "UK (Mix)",
    # -- Russia --
    "russia_M_25k": "Russia (M)",
    "russia_F_25k": "Russia (F)",
    "russia_Mix_50k": "Russia (Mix)",
    # -- Egypt --
    "egypt_M_25k": "Egypt (M)",
    "egypt_F_25k": "Egypt (F)",
    "egypt_Mix_50k": "Egypt (Mix)",
    # -- Nigeria --
    "nigeria_M_25k": "Nigeria (M)",
    "nigeria_F_25k": "Nigeria (F)",
    "nigeria_Mix_50k": "Nigeria (Mix)",
    # -- South Africa --
    "south_africa_M_25k": "South Africa (M)",
    "south_africa_F_25k": "South Africa (F)",
    "south_africa_Mix_50k": "South Africa (Mix)",
    # -- Arab --
    "arab_M_25k": "Arab (M)",
    "arab_F_25k": "Arab (F)",
    "arab_Mix_50k": "Arab (Mix)",
    # -- India --
    "india_M_25k": "India (M)",
    "india_F_25k": "India (F)",
    "india_Mix_50k": "India (Mix)",
    # -- Philippines --
    "philippines_M_25k": "Philippines (M)",
    "philippines_F_25k": "Philippines (F)",
    "philippines_Mix_50k": "Philippines (Mix)",
    # -- Turkey --
    "turkey_M_25k": "Turkey (M)",
    "turkey_F_25k": "Turkey (F)",
    "turkey_Mix_50k": "Turkey (Mix)",
}


def seed_builtin_names():
    """Auto-import built-in GEO name packs on first startup only.
    Uses a marker file to track which packs were already seeded,
    so user-deleted packs won't be re-imported on restart.
    """
    if not os.path.isdir(BUILTIN_NAMES_DIR):
        return

    # Marker file tracks which built-in packs we already seeded
    marker_path = os.path.join(NAMES_DIR, ".seeded")
    already_seeded = set()
    if os.path.exists(marker_path):
        with open(marker_path, "r", encoding="utf-8") as f:
            already_seeded = {line.strip() for line in f if line.strip()}

    db = SessionLocal()
    try:
        existing = {p.name for p in db.query(NamePack).all()}
        seeded = 0
        new_seeded = set()

        for filename in sorted(os.listdir(BUILTIN_NAMES_DIR)):
            if not filename.endswith(".txt"):
                continue

            geo_key = os.path.splitext(filename)[0]
            pack_label = GEO_LABELS.get(geo_key, f"{geo_key}")

            # Skip if already seeded before (even if user deleted it)
            if filename in already_seeded:
                new_seeded.add(filename)
                continue

            # Skip if already exists in DB by name
            if pack_label in existing:
                new_seeded.add(filename)
                continue

            src = os.path.join(BUILTIN_NAMES_DIR, filename)
            dst = os.path.join(NAMES_DIR, filename)

            # Copy file to user_data/names/
            shutil.copy2(src, dst)

            # Count names
            count = 0
            with open(dst, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        count += 1

            pack = NamePack(
                name=pack_label,
                file_path=dst,  # absolute path
                total_count=count,
            )
            db.add(pack)
            seeded += 1
            new_seeded.add(filename)
            logger.info(f"[Names] Seeded: {pack_label} ({count} names)")

        if seeded:
            db.commit()
            logger.info(f"[Names] [OK] Seeded {seeded} built-in GEO name packs")

        # Save marker file with all seeded filenames
        with open(marker_path, "w", encoding="utf-8") as f:
            f.write("\n".join(sorted(new_seeded)))

        # Fix any relative or stale paths from previous versions
        fixed = 0
        for pack in db.query(NamePack).all():
            fp = pack.file_path
            # Convert relative paths to absolute using NAMES_DIR
            if fp and not os.path.isabs(fp):
                basename = os.path.basename(fp)
                new_path = os.path.join(NAMES_DIR, basename)
                pack.file_path = new_path
                fixed += 1
            elif fp and os.path.isabs(fp):
                # Already absolute - check if it points to old location
                basename = os.path.basename(fp)
                expected = os.path.join(NAMES_DIR, basename)
                if fp != expected and not os.path.exists(fp) and os.path.exists(expected):
                    pack.file_path = expected
                    fixed += 1
        if fixed:
            db.commit()
            logger.info(f"[Names] Fixed {fixed} paths -> absolute")

        # Migrate old pack names to clean GEO format
        # (e.g., "Argentina - 5000" â†’ "Argentina")
        old_to_new = {}
        for geo_key, clean_label in GEO_LABELS.items():
            filename = f"{geo_key}.txt"
            for pack in db.query(NamePack).all():
                if pack.file_path and os.path.basename(pack.file_path) == filename:
                    if pack.name != clean_label:
                        old_to_new[pack.id] = (pack.name, clean_label)
                        pack.name = clean_label
        if old_to_new:
            db.commit()
            for pid, (old, new) in old_to_new.items():
                logger.info(f"[Names] Renamed: '{old}' â†’ '{new}'")
            logger.info(f"[Names] Migrated {len(old_to_new)} pack names to clean GEO format")

    except Exception as e:
        logger.error(f"[Names] Seed error: {e}")
    finally:
        db.close()


@router.get("/")
async def list_name_packs(db: Session = Depends(get_db)):
    packs = db.query(NamePack).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "total_count": p.total_count,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in packs
    ]


@router.get("/{pack_id}/preview")
async def preview_name_pack(pack_id: int, db: Session = Depends(get_db)):
    """Return all names from a pack."""
    pack = db.query(NamePack).filter(NamePack.id == pack_id).first()
    if not pack:
        return {"error": "Pack not found", "names": []}
    import os
    if not os.path.exists(pack.file_path):
        return {"error": "File not found", "names": [], "name": pack.name}
    lines = []
    try:
        with open(pack.file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    lines.append(line)
    except Exception:
        pass
    return {"name": pack.name, "total": pack.total_count, "names": lines}


def _parse_name_line(line: str) -> tuple[str, str] | None:
    """Parse a name line: 'First,Last' or 'First Last' or just 'First'."""
    line = line.strip()
    if not line or line.startswith('#'):
        return None

    if ',' in line:
        parts = [p.strip() for p in line.split(',', 1)]
    elif '\t' in line:
        parts = [p.strip() for p in line.split('\t', 1)]
    else:
        parts = line.split(None, 1)

    first = parts[0] if len(parts) > 0 else None
    last = parts[1] if len(parts) > 1 else ""

    if not first:
        return None
    return (first, last)


@router.post("/upload")
async def upload_name_pack(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = (await file.read()).decode("utf-8", errors="ignore")
    lines = content.strip().split("\n")

    names = []
    for line in lines:
        parsed = _parse_name_line(line)
        if parsed:
            names.append(parsed)

    if not names:
        return {"error": "No names found in file"}

    # Save file
    pack_name = os.path.splitext(file.filename)[0]
    file_path = os.path.join(NAMES_DIR, f"{pack_name}.txt")
    counter = 1
    while os.path.exists(file_path):
        file_path = os.path.join(NAMES_DIR, f"{pack_name}_{counter}.txt")
        counter += 1

    with open(file_path, "w", encoding="utf-8") as f:
        for first, last in names:
            f.write(f"{first},{last}\n")

    pack = NamePack(
        name=pack_name,
        file_path=file_path,
        total_count=len(names),
    )
    db.add(pack)
    db.commit()

    logger.info(f"Name pack '{pack_name}' uploaded: {len(names)} names")
    return {"id": pack.id, "name": pack_name, "count": len(names)}


from pydantic import BaseModel


class NameTextUpload(BaseModel):
    name: str = ""
    text: str


@router.post("/upload-text")
async def upload_names_text(req: NameTextUpload, db: Session = Depends(get_db)):
    """Upload names from pasted text (first,last per line)."""
    lines = req.text.strip().split("\n")
    names = []
    for line in lines:
        parsed = _parse_name_line(line)
        if parsed:
            names.append(parsed)

    if not names:
        return {"error": "No names found. Format: first,last (one per line)"}

    import time
    pack_name = req.name.strip() or f"paste_{len(names)}_names"
    file_path = os.path.join(NAMES_DIR, f"{int(time.time())}_{pack_name}.txt")

    with open(file_path, "w", encoding="utf-8") as f:
        for first, last in names:
            f.write(f"{first},{last}\n")

    pack = NamePack(
        name=pack_name,
        file_path=file_path,
        total_count=len(names),
    )
    db.add(pack)
    db.commit()

    logger.info(f"Name pack '{pack_name}' from text: {len(names)} names")
    return {"id": pack.id, "name": pack_name, "count": len(names)}

@router.post("/batch-delete")
async def batch_delete_names(req: dict, db: Session = Depends(get_db)):
    """Delete multiple name packs by IDs."""
    ids = req.get("ids", [])
    if not ids:
        return {"deleted": 0}
    packs = db.query(NamePack).filter(NamePack.id.in_(ids)).all()
    deleted_files = []
    for p in packs:
        try:
            if p.file_path and os.path.exists(p.file_path):
                deleted_files.append(os.path.basename(p.file_path))
                os.remove(p.file_path)
        except Exception:
            pass
        db.delete(p)
    db.commit()
    # Mark deleted built-in packs in .seeded so they won't re-appear
    _mark_seeded(deleted_files)
    return {"deleted": len(packs)}

@router.delete("/{pack_id}")
async def delete_name_pack(pack_id: int, db: Session = Depends(get_db)):
    pack = db.query(NamePack).filter(NamePack.id == pack_id).first()
    if not pack:
        return {"error": "Pack not found"}

    deleted_file = None
    if pack.file_path and os.path.exists(pack.file_path):
        deleted_file = os.path.basename(pack.file_path)
        os.remove(pack.file_path)

    db.delete(pack)
    db.commit()
    # Mark in .seeded so it won't re-appear on restart
    if deleted_file:
        _mark_seeded([deleted_file])
    return {"status": "deleted"}


def _mark_seeded(filenames: list[str]):
    """Add filenames to .seeded marker to prevent re-import on restart."""
    if not filenames:
        return
    marker_path = os.path.join(NAMES_DIR, ".seeded")
    existing = set()
    if os.path.exists(marker_path):
        with open(marker_path, "r", encoding="utf-8") as f:
            existing = {line.strip() for line in f if line.strip()}
    existing.update(filenames)
    with open(marker_path, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(existing)))


@router.get("/random")
async def get_random_name(pack_ids: str = "", db: Session = Depends(get_db)):
    """Get a random name from selected packs. pack_ids = comma-separated IDs."""
    ids = [int(x) for x in pack_ids.split(",") if x.strip().isdigit()] if pack_ids else []

    if ids:
        packs = db.query(NamePack).filter(NamePack.id.in_(ids)).all()
    else:
        packs = db.query(NamePack).all()

    if not packs:
        return {"first_name": "Alex", "last_name": "Johnson"}

    # Collect all names from all selected packs
    all_names = []
    for pack in packs:
        if os.path.exists(pack.file_path):
            with open(pack.file_path, "r", encoding="utf-8") as f:
                for line in f:
                    parsed = _parse_name_line(line)
                    if parsed:
                        all_names.append(parsed)

    if not all_names:
        return {"first_name": "Alex", "last_name": "Johnson"}

    first, last = random.choice(all_names)
    return {"first_name": first, "last_name": last}

