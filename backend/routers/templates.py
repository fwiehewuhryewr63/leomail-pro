from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Template
from ..schemas import TemplateCreate
from loguru import logger
import zipfile
import json
import io
import re
import os


router = APIRouter(prefix="/api/templates", tags=["templates"])

TEMPLATE_VARS = ["LINK", "USERNAME", "NAME", "FIRSTNAME", "LASTNAME", "EMAILNAME", "USER"]


def detect_variables(text: str) -> list:
    """Detect {{VAR}} variables in text."""
    found = set()
    upper = text.upper()
    for var in TEMPLATE_VARS:
        if "{{" + var + "}}" in upper:
            found.add(var)
    return sorted(list(found))


def split_embedded_subject(content: str) -> tuple[str | None, str]:
    """
    Generator legacy packs may store "Subject: ..." as the first line inside the
    template file while also providing the same subject in manifest.json.
    Return the embedded subject (if present) and the cleaned body.
    """
    if not content:
        return None, ""

    lines = content.split("\n", 1)
    first_line = lines[0].strip()
    if first_line.lower().startswith("subject:"):
        embedded_subject = first_line[8:].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        return embedded_subject, body

    return None, content


@router.get("/packs")
async def list_template_packs(db: Session = Depends(get_db)):
    """List unique packs with count."""
    from sqlalchemy import func
    packs = db.query(
        Template.pack_name, func.count(Template.id)
    ).group_by(Template.pack_name).all()
    
    return [
        {"name": p[0], "count": p[1]} 
        for p in packs if p[0]
    ]


@router.get("/")
async def list_templates(db: Session = Depends(get_db)):
    templates = db.query(Template).order_by(Template.created_at.desc()).all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "subject": t.subject,
            "content_type": t.content_type,
            "language": t.language,
            "pack_name": t.pack_name,
            "niche": t.niche or "",
            "variables": t.variables or [],
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "body_preview": t.body[:200] if t.body else ""
        }
        for t in templates
    ]


@router.post("/")
async def create_template(req: TemplateCreate, db: Session = Depends(get_db)):
    variables = detect_variables(req.subject + " " + req.body)
    template = Template(
        name=req.name,
        subject=req.subject,
        body=req.body,
        content_type=req.content_type,
        language=req.language,
        niche=req.niche or None,
        variables=variables,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return {"id": template.id, "status": "created", "variables": variables}


@router.get("/{template_id}")
async def get_template(template_id: int, db: Session = Depends(get_db)):
    t = db.query(Template).filter(Template.id == template_id).first()
    if not t:
        return {"error": "Template not found"}
    return {
        "id": t.id,
        "name": t.name,
        "subject": t.subject,
        "body": t.body,
        "content_type": t.content_type,
        "language": t.language,
        "pack_name": t.pack_name,
        "variables": t.variables or [],
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


@router.post("/batch-delete")
async def batch_delete_templates(req: dict, db: Session = Depends(get_db)):
    """Delete multiple templates by IDs."""
    ids = req.get("ids", [])
    if not ids:
        return {"deleted": 0}
    count = db.query(Template).filter(Template.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    return {"deleted": count}

@router.delete("/pack/{pack_name}")
async def delete_pack(pack_name: str, db: Session = Depends(get_db)):
    """Delete all templates from a pack."""
    templates = db.query(Template).filter(Template.pack_name == pack_name).all()
    count = len(templates)
    for t in templates:
        db.delete(t)
    db.commit()
    return {"status": "deleted", "count": count}


@router.delete("/{template_id}")
async def delete_template(template_id: int, db: Session = Depends(get_db)):
    t = db.query(Template).filter(Template.id == template_id).first()
    if not t:
        return {"error": "Template not found"}
    db.delete(t)
    db.commit()
    return {"status": "deleted"}


@router.post("/import-zip")
async def import_zip(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Import templates from a ZIP archive.
    
    Supported formats (auto-detected):
    
    1. Folder-per-letter (preferred):
       templates/letter_001/subject.txt + body.txt (or body.html)
       Optional manifest.json for pack name and template names.
    
    2. manifest.json + templates/*.html (legacy):
       manifest references files with subject in JSON.
    
    3. Flat files (fallback):
       .html/.txt files with first line "Subject: ..."
    """
    try:
        contents = await file.read()
        zf = zipfile.ZipFile(io.BytesIO(contents))
    except Exception as e:
        return {"error": f"Invalid ZIP file: {str(e)}"}

    file_list = zf.namelist()
    imported = 0
    errors = []
    pack_name = file.filename.replace(".zip", "") if file.filename else "imported"

    # Parse manifest.json if exists
    manifest = None
    manifest_paths = [f for f in file_list if f.endswith("manifest.json")]
    if manifest_paths:
        try:
            manifest_data = zf.read(manifest_paths[0]).decode("utf-8")
            manifest = json.loads(manifest_data)
            if manifest.get("pack_name"):
                pack_name = manifest["pack_name"]
        except Exception as e:
            errors.append(f"manifest.json parse error: {e}")
            manifest = None

    # ─── MODE 1: Folder-per-letter (detect subject.txt files) ───
    subject_files = [f for f in file_list if f.endswith("subject.txt") and not f.startswith("__MACOSX")]

    if subject_files:
        # Build manifest names lookup
        manifest_names = {}
        if manifest and manifest.get("templates"):
            for tmpl_info in manifest["templates"]:
                folder = tmpl_info.get("folder", "")
                name = tmpl_info.get("name", folder)
                manifest_names[folder] = name

        for subj_path in subject_files:
            try:
                folder_path = os.path.dirname(subj_path)
                folder_name = os.path.basename(folder_path)

                # Read subject
                subject = zf.read(subj_path).decode("utf-8", errors="replace").strip()
                # Take first line only (subject should be 1 line)
                subject = subject.split("\n")[0].strip()

                # Find body file (body.txt, body.html, or any .html/.txt in folder)
                body = None
                content_type = "text"
                
                body_candidates = [
                    (os.path.join(folder_path, "body.html").replace("\\", "/"), "html"),
                    (os.path.join(folder_path, "body.htm").replace("\\", "/"), "html"),
                    (os.path.join(folder_path, "body.txt").replace("\\", "/"), "text"),
                ]
                for body_path, ct in body_candidates:
                    if body_path in file_list:
                        body = zf.read(body_path).decode("utf-8", errors="replace").strip()
                        content_type = ct
                        break

                # Fallback: any file in same folder that isn't subject.txt
                if body is None:
                    for f in file_list:
                        if f.startswith(folder_path + "/") and f != subj_path:
                            if f.endswith((".html", ".htm", ".txt")):
                                body = zf.read(f).decode("utf-8", errors="replace").strip()
                                content_type = "html" if f.endswith((".html", ".htm")) else "text"
                                break

                if body is None:
                    errors.append(f"{folder_name}: body file not found")
                    continue

                # Name from manifest or folder name
                name = manifest_names.get(folder_name, folder_name)

                variables = detect_variables(subject + " " + body)
                template = Template(
                    name=name,
                    subject=subject,
                    body=body,
                    content_type=content_type,
                    pack_name=pack_name,
                    variables=variables,
                )
                db.add(template)
                imported += 1

            except Exception as e:
                errors.append(f"{subj_path}: {e}")

    # ─── MODE 2: manifest.json with file references (legacy) ───
    elif manifest and manifest.get("templates"):
        base_dir = os.path.dirname(manifest_paths[0])
        for tmpl_info in manifest["templates"]:
            tmpl_file = tmpl_info.get("file", "")
            subject = tmpl_info.get("subject", "No Subject")
            name = tmpl_info.get("name", tmpl_file.replace(".html", ""))

            search_paths = [
                os.path.join(base_dir, "templates", tmpl_file).replace("\\", "/"),
                os.path.join(base_dir, tmpl_file).replace("\\", "/"),
                f"templates/{tmpl_file}",
                tmpl_file,
            ]
            body = None
            for sp in search_paths:
                if sp in file_list:
                    body = zf.read(sp).decode("utf-8", errors="replace")
                    break

            if body is None:
                errors.append(f"File not found: {tmpl_file}")
                continue

            embedded_subject, clean_body = split_embedded_subject(body)
            if embedded_subject and subject == "No Subject":
                subject = embedded_subject
            body = clean_body if embedded_subject is not None else body

            content_type = "html" if tmpl_file.endswith((".html", ".htm")) else "text"
            variables = detect_variables(subject + " " + body)
            template = Template(
                name=name,
                subject=subject,
                body=body,
                content_type=content_type,
                pack_name=pack_name,
                variables=variables,
            )
            db.add(template)
            imported += 1

    # ─── MODE 3: Flat files (fallback) ───
    else:
        text_files = [
            f for f in file_list
            if f.endswith((".html", ".htm", ".txt"))
            and not f.startswith("__MACOSX")
            and not f.endswith("manifest.json")
        ]
        for tf in text_files:
            try:
                content = zf.read(tf).decode("utf-8", errors="replace")
                lines = content.strip().split("\n", 1)

                # Check if first line is Subject:
                if lines[0].strip().lower().startswith("subject:"):
                    subject = lines[0].strip()[8:].strip()
                    body = lines[1].strip() if len(lines) > 1 else ""
                else:
                    subject = os.path.basename(tf).rsplit(".", 1)[0]
                    body = content

                name = os.path.basename(tf).rsplit(".", 1)[0]
                content_type = "html" if tf.endswith((".html", ".htm")) else "text"
                variables = detect_variables(subject + " " + body)

                template = Template(
                    name=name,
                    subject=subject,
                    body=body,
                    content_type=content_type,
                    pack_name=pack_name,
                    variables=variables,
                )
                db.add(template)
                imported += 1
            except Exception as e:
                errors.append(f"{tf}: {e}")

    db.commit()
    logger.info(f"Imported {imported} templates from ZIP '{pack_name}'")

    return {
        "status": "ok",
        "imported": imported,
        "errors": errors,
        "pack_name": pack_name,
    }
