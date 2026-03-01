"""
Leomail v4 - Campaign Router
CRUD operations + bulk import for templates, ESP links, recipients.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import random
import string

from ..database import get_db
from ..models import (
    Campaign, CampaignStatus, CampaignTemplate, CampaignLink, CampaignRecipient,
)

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────

class CampaignCreate(BaseModel):
    name: str
    geo: str
    niche: str = "general"
    name_pack: str = "brazil_5k"
    providers: list[str] = ["gmail", "yahoo"]
    birth_threads: int = 10
    send_threads: int = 20
    link_mode: str = "hyperlink"
    # Send settings
    emails_per_day_min: int = 25
    emails_per_day_max: int = 75
    delay_min: int = 30
    delay_max: int = 180
    same_provider: bool = False
    max_link_uses: int = 0
    max_link_cycles: int = 0
    # Account source
    use_existing: bool = False
    farm_ids: list[int] = []
    # Resource selection (IDs from global pools)
    template_ids: list[int] = []
    database_ids: list[int] = []
    link_pack_ids: list[int] = []


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    geo: Optional[str] = None
    niche: Optional[str] = None
    name_pack: Optional[str] = None
    providers: Optional[list[str]] = None
    birth_threads: Optional[int] = None
    send_threads: Optional[int] = None
    link_mode: Optional[str] = None
    # Send settings
    emails_per_day_min: Optional[int] = None
    emails_per_day_max: Optional[int] = None
    delay_min: Optional[int] = None
    delay_max: Optional[int] = None
    same_provider: Optional[bool] = None
    max_link_uses: Optional[int] = None
    max_link_cycles: Optional[int] = None
    # Account source
    use_existing: Optional[bool] = None
    farm_ids: Optional[list[int]] = None


class BulkTextImport(BaseModel):
    """Raw text import - one item per line."""
    content: str          # raw text pasted or from file
    max_uses: int = 100   # for links: max uses per link


# ─── Campaign CRUD ────────────────────────────────────────────────────────────

@router.get("")
async def list_campaigns(db: Session = Depends(get_db)):
    """List all campaigns with summary stats."""
    campaigns = db.query(Campaign).order_by(Campaign.created_at.desc()).all()
    result = []
    for c in campaigns:
        total_recipients = db.query(CampaignRecipient).filter(
            CampaignRecipient.campaign_id == c.id
        ).count()
        sent_recipients = db.query(CampaignRecipient).filter(
            CampaignRecipient.campaign_id == c.id,
            CampaignRecipient.sent == True  # noqa: E712
        ).count()
        active_links = db.query(CampaignLink).filter(
            CampaignLink.campaign_id == c.id,
            CampaignLink.active == True  # noqa: E712
        ).count()
        total_links = db.query(CampaignLink).filter(
            CampaignLink.campaign_id == c.id
        ).count()
        active_templates = db.query(CampaignTemplate).filter(
            CampaignTemplate.campaign_id == c.id,
            CampaignTemplate.active == True  # noqa: E712
        ).count()

        result.append({
            "id": c.id,
            "name": c.name,
            "geo": c.geo,
            "niche": c.niche,
            "status": c.status,
            "stop_reason": c.stop_reason,
            "name_pack": c.name_pack,
            "providers": c.providers or [],
            "birth_threads": c.birth_threads,
            "send_threads": c.send_threads,
            "link_mode": c.link_mode,
            "total_sent": c.total_sent,
            "total_errors": c.total_errors,
            "accounts_born": c.accounts_born,
            "accounts_dead": c.accounts_dead,
            "recipients_total": total_recipients,
            "recipients_sent": sent_recipients,
            "links_active": active_links,
            "links_total": total_links,
            "templates_active": active_templates,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })
    return result


@router.post("")
async def create_campaign(req: CampaignCreate, db: Session = Depends(get_db)):
    """Create a new campaign with full settings and auto-import resources."""
    campaign = Campaign(
        name=req.name,
        geo=req.geo.upper(),
        niche=req.niche,
        name_pack=req.name_pack,
        providers=req.providers,
        gender="female",
        birth_threads=req.birth_threads,
        send_threads=req.send_threads,
        link_mode=req.link_mode,
        # Send settings
        emails_per_day_min=req.emails_per_day_min,
        emails_per_day_max=req.emails_per_day_max,
        delay_min=req.delay_min,
        delay_max=req.delay_max,
        same_provider=req.same_provider,
        max_link_uses=req.max_link_uses,
        max_link_cycles=req.max_link_cycles,
        # Account source
        use_existing=req.use_existing,
        farm_ids=req.farm_ids,
        status=CampaignStatus.DRAFT,
    )
    db.add(campaign)
    db.flush()  # get campaign.id

    imported = {"templates": 0, "links": 0, "recipients": 0}

    # ── Import templates from global pool ──
    if req.template_ids:
        from ..models import Template as GlobalTemplate
        templates = db.query(GlobalTemplate).filter(GlobalTemplate.id.in_(req.template_ids)).all()
        for t in templates:
            ct = CampaignTemplate(
                campaign_id=campaign.id,
                subject=t.subject,
                body_html=t.body,
                style=t.content_type,
                active=True,
            )
            db.add(ct)
            imported["templates"] += 1

    # ── Import links from link packs ──
    if req.link_pack_ids:
        from ..models import LinkDatabase
        from ..config import CONFIG_DIR
        packs = db.query(LinkDatabase).filter(LinkDatabase.id.in_(req.link_pack_ids)).all()
        for pack in packs:
            try:
                full_path = CONFIG_DIR / pack.file_path
                if full_path.exists():
                    with open(full_path, "r", encoding="utf-8") as f:
                        for line in f:
                            url = line.strip()
                            if url.startswith("http"):
                                cl = CampaignLink(
                                    campaign_id=campaign.id,
                                    esp_url=url,
                                    max_uses=req.max_link_uses if req.max_link_uses > 0 else 100,
                                    active=True,
                                )
                                db.add(cl)
                                imported["links"] += 1
            except Exception as e:
                logger.error(f"Link import error for pack {pack.id}: {e}")

    # ── Import recipients from databases ──
    if req.database_ids:
        from ..models import RecipientDatabase
        from ..config import CONFIG_DIR
        import json as _json
        rd_list = db.query(RecipientDatabase).filter(RecipientDatabase.id.in_(req.database_ids)).all()
        for rd in rd_list:
            try:
                # Try direct path first, then relative to CONFIG_DIR
                from pathlib import Path as _Path
                fp = _Path(rd.file_path)
                if not fp.exists():
                    fp = CONFIG_DIR / rd.file_path

                if fp.exists() and fp.suffix == '.json':
                    # JSON format (standard)
                    entries = _json.loads(fp.read_text(encoding='utf-8'))
                    for entry in entries:
                        email = (entry.get('email', '') or '').strip().lower()
                        if '@' in email:
                            cr = CampaignRecipient(
                                campaign_id=campaign.id,
                                email=email,
                                first_name=entry.get('first_name', '') or '',
                                sent=False,
                            )
                            db.add(cr)
                            imported["recipients"] += 1
                elif fp.exists():
                    # Legacy txt format: email or email,Name
                    with open(fp, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            parts = [p.strip() for p in line.split(",")]
                            email = parts[0].lower()
                            name = parts[1] if len(parts) > 1 else ""
                            if "@" in email:
                                cr = CampaignRecipient(
                                    campaign_id=campaign.id,
                                    email=email,
                                    first_name=name,
                                    sent=False,
                                )
                                db.add(cr)
                                imported["recipients"] += 1
            except Exception as e:
                logger.error(f"Recipient import error for db {rd.id}: {e}")

    db.commit()
    db.refresh(campaign)

    logger.info(
        f"Campaign '{campaign.name}' created: "
        f"{imported['templates']} templates, {imported['links']} links, {imported['recipients']} recipients"
    )

    return {
        "id": campaign.id,
        "name": campaign.name,
        "status": campaign.status,
        "imported": imported,
    }


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: int, db: Session = Depends(get_db)):
    """Get campaign details with full stats."""
    c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not c:
        raise HTTPException(404, "Campaign not found")

    total_r = db.query(CampaignRecipient).filter(CampaignRecipient.campaign_id == c.id).count()
    sent_r = db.query(CampaignRecipient).filter(
        CampaignRecipient.campaign_id == c.id,
        CampaignRecipient.sent == True  # noqa: E712
    ).count()

    templates = db.query(CampaignTemplate).filter(CampaignTemplate.campaign_id == c.id).all()
    links_total = db.query(CampaignLink).filter(CampaignLink.campaign_id == c.id).count()
    links_active = db.query(CampaignLink).filter(
        CampaignLink.campaign_id == c.id,
        CampaignLink.active == True  # noqa: E712
    ).count()

    return {
        "id": c.id,
        "name": c.name,
        "geo": c.geo,
        "niche": c.niche,
        "status": c.status,
        "stop_reason": c.stop_reason,
        "name_pack": c.name_pack,
        "providers": c.providers or [],
        "gender": c.gender,
        "birth_threads": c.birth_threads,
        "send_threads": c.send_threads,
        "link_mode": c.link_mode,
        "total_sent": c.total_sent,
        "total_errors": c.total_errors,
        "accounts_born": c.accounts_born,
        "accounts_dead": c.accounts_dead,
        "recipients_total": total_r,
        "recipients_sent": sent_r,
        "progress_pct": int((sent_r / total_r * 100)) if total_r > 0 else 0,
        "links_total": links_total,
        "links_active": links_active,
        "templates": [
            {"id": t.id, "subject": t.subject, "style": t.style,
             "use_count": t.use_count, "active": t.active}
            for t in templates
        ],
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


@router.put("/{campaign_id}")
async def update_campaign(campaign_id: int, req: CampaignUpdate, db: Session = Depends(get_db)):
    """Update campaign settings (only when draft or paused)."""
    c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not c:
        raise HTTPException(404, "Campaign not found")
    if c.status == CampaignStatus.RUNNING:
        raise HTTPException(400, "Cannot update running campaign - pause first")

    for field, value in req.dict(exclude_none=True).items():
        if field == "geo" and value:
            value = value.upper()
        setattr(c, field, value)

    db.commit()
    return {"ok": True}


@router.delete("/{campaign_id}")
async def delete_campaign(campaign_id: int, db: Session = Depends(get_db)):
    """Delete campaign and all related data (cascade)."""
    c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not c:
        raise HTTPException(404, "Campaign not found")
    if c.status == CampaignStatus.RUNNING:
        raise HTTPException(400, "Cannot delete running campaign - stop first")

    db.delete(c)
    db.commit()
    return {"ok": True, "deleted": c.name}


# ─── Campaign Actions ─────────────────────────────────────────────────────────

@router.post("/{campaign_id}/start")
async def start_campaign(campaign_id: int, db: Session = Depends(get_db)):
    """Start or resume a campaign."""
    c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not c:
        raise HTTPException(404, "Campaign not found")
    if c.status == CampaignStatus.RUNNING:
        raise HTTPException(400, "Campaign already running")

    # Pre-flight checks
    templates = db.query(CampaignTemplate).filter(
        CampaignTemplate.campaign_id == c.id, CampaignTemplate.active == True  # noqa
    ).count()
    links = db.query(CampaignLink).filter(
        CampaignLink.campaign_id == c.id, CampaignLink.active == True  # noqa
    ).count()
    recipients = db.query(CampaignRecipient).filter(
        CampaignRecipient.campaign_id == c.id, CampaignRecipient.sent == False  # noqa
    ).count()

    issues = []
    if templates == 0:
        issues.append("No active templates")
    if links == 0:
        issues.append("No active ESP links")
    if recipients == 0:
        issues.append("No unsent recipients")
    if not c.providers:
        issues.append("No providers selected")

    if issues:
        return {"ok": False, "issues": issues}

    c.status = CampaignStatus.RUNNING
    c.stop_reason = None
    db.commit()

    # Start Blitz Engine
    from ..modules.blitz_engine import start_blitz, get_active_campaign
    existing = get_active_campaign(c.id)
    if existing:
        await existing.resume()
    else:
        await start_blitz(c.id)
    return {"ok": True, "status": "running"}


@router.post("/{campaign_id}/pause")
async def pause_campaign(campaign_id: int, db: Session = Depends(get_db)):
    """Pause a running campaign."""
    c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not c:
        raise HTTPException(404, "Campaign not found")

    c.status = CampaignStatus.PAUSED
    db.commit()
    # Signal Blitz Engine to pause
    from ..modules.blitz_engine import pause_blitz
    await pause_blitz(c.id)
    return {"ok": True, "status": "paused"}


@router.post("/{campaign_id}/stop")
async def stop_campaign(campaign_id: int, db: Session = Depends(get_db)):
    """Fully stop a campaign."""
    c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not c:
        raise HTTPException(404, "Campaign not found")

    # Signal Blitz Engine to stop
    from ..modules.blitz_engine import stop_blitz
    await stop_blitz(c.id, "Manual stop")

    c.status = CampaignStatus.STOPPED
    c.stop_reason = "Manual stop"
    db.commit()
    return {"ok": True, "status": "stopped"}


# ─── Template Import ──────────────────────────────────────────────────────────

@router.post("/{campaign_id}/templates/import")
async def import_templates(campaign_id: int, req: BulkTextImport, db: Session = Depends(get_db)):
    """Import templates from text. Separator: ---TEMPLATE---"""
    c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not c:
        raise HTTPException(404, "Campaign not found")

    blocks = req.content.split("---TEMPLATE---")
    added = 0

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # Parse Subject: and Body:
        subject = ""
        body = ""
        lines = block.split("\n")
        body_start = 0

        for i, line in enumerate(lines):
            if line.strip().lower().startswith("subject:"):
                subject = line.split(":", 1)[1].strip()
            elif line.strip().lower().startswith("body:"):
                body_start = i + 1
                break

        if body_start > 0:
            body = "\n".join(lines[body_start:]).strip()
        elif not subject:
            # No headers - first line = subject, rest = body
            if lines:
                subject = lines[0].strip()
                body = "\n".join(lines[1:]).strip()

        if not subject or not body:
            continue

        tmpl = CampaignTemplate(
            campaign_id=c.id,
            subject=subject,
            body_html=body,
        )
        db.add(tmpl)
        added += 1

    db.commit()
    return {"ok": True, "added": added}


@router.get("/{campaign_id}/templates")
async def list_templates(campaign_id: int, db: Session = Depends(get_db)):
    """List all templates for a campaign."""
    templates = db.query(CampaignTemplate).filter(
        CampaignTemplate.campaign_id == campaign_id
    ).order_by(CampaignTemplate.id).all()
    return [
        {"id": t.id, "subject": t.subject, "body_html": t.body_html,
         "style": t.style, "use_count": t.use_count, "active": t.active}
        for t in templates
    ]


@router.delete("/{campaign_id}/templates/{template_id}")
async def delete_template(campaign_id: int, template_id: int, db: Session = Depends(get_db)):
    """Delete a specific template."""
    t = db.query(CampaignTemplate).filter(
        CampaignTemplate.id == template_id,
        CampaignTemplate.campaign_id == campaign_id
    ).first()
    if not t:
        raise HTTPException(404, "Template not found")
    db.delete(t)
    db.commit()
    return {"ok": True}


# ─── ESP Link Import ──────────────────────────────────────────────────────────

@router.post("/{campaign_id}/links/import")
async def import_links(campaign_id: int, req: BulkTextImport, db: Session = Depends(get_db)):
    """Import ESP tracking links - one URL per line."""
    c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not c:
        raise HTTPException(404, "Campaign not found")

    added = 0
    skipped = 0
    for line in req.content.strip().split("\n"):
        url = line.strip()
        if not url or url.startswith("#"):
            continue
        if not url.startswith("http"):
            skipped += 1
            continue

        # Check duplicate
        existing = db.query(CampaignLink).filter(
            CampaignLink.campaign_id == c.id,
            CampaignLink.esp_url == url
        ).first()
        if existing:
            skipped += 1
            continue

        link = CampaignLink(
            campaign_id=c.id,
            esp_url=url,
            max_uses=req.max_uses,
        )
        db.add(link)
        added += 1

    db.commit()
    return {"ok": True, "added": added, "skipped": skipped}


@router.get("/{campaign_id}/links")
async def list_links(campaign_id: int, db: Session = Depends(get_db)):
    """List all ESP links for a campaign."""
    links = db.query(CampaignLink).filter(
        CampaignLink.campaign_id == campaign_id
    ).order_by(CampaignLink.id).all()
    return {
        "total": len(links),
        "active": sum(1 for l in links if l.active),
        "links": [
            {"id": l.id, "esp_url": l.esp_url, "use_count": l.use_count,
             "max_uses": l.max_uses, "active": l.active}
            for l in links[:100]  # limit to first 100 for display
        ]
    }


# ─── Recipient Import ─────────────────────────────────────────────────────────

@router.post("/{campaign_id}/recipients/import")
async def import_recipients(campaign_id: int, req: BulkTextImport, db: Session = Depends(get_db)):
    """Import recipient emails - one per line."""
    c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not c:
        raise HTTPException(404, "Campaign not found")

    added = 0
    skipped = 0
    seen = set()

    # Get existing emails to avoid duplicates
    existing_emails = set(
        e[0] for e in db.query(CampaignRecipient.email).filter(
            CampaignRecipient.campaign_id == c.id
        ).all()
    )

    batch = []
    for line in req.content.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Parse: email or email,Name
        parts = [p.strip() for p in line.split(",")]
        email = parts[0].lower()
        first_name = parts[1] if len(parts) > 1 else ""

        if "@" not in email:
            skipped += 1
            continue
        if email in existing_emails or email in seen:
            skipped += 1
            continue

        seen.add(email)
        batch.append(CampaignRecipient(campaign_id=c.id, email=email, first_name=first_name))
        added += 1

        # Batch insert every 1000
        if len(batch) >= 1000:
            db.bulk_save_objects(batch)
            batch = []

    if batch:
        db.bulk_save_objects(batch)
    db.commit()

    return {"ok": True, "added": added, "skipped": skipped}


@router.get("/{campaign_id}/recipients/stats")
async def recipient_stats(campaign_id: int, db: Session = Depends(get_db)):
    """Get recipient statistics."""
    total = db.query(CampaignRecipient).filter(
        CampaignRecipient.campaign_id == campaign_id
    ).count()
    sent = db.query(CampaignRecipient).filter(
        CampaignRecipient.campaign_id == campaign_id,
        CampaignRecipient.sent == True  # noqa
    ).count()
    return {"total": total, "sent": sent, "remaining": total - sent}


# ─── Pre-flight Check ─────────────────────────────────────────────────────────

@router.get("/{campaign_id}/preflight")
async def preflight_check(campaign_id: int, db: Session = Depends(get_db)):
    """Check all resources before starting a campaign."""
    c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not c:
        raise HTTPException(404, "Campaign not found")

    checks = {}

    # Templates
    active_templates = db.query(CampaignTemplate).filter(
        CampaignTemplate.campaign_id == c.id, CampaignTemplate.active == True  # noqa
    ).count()
    checks["templates"] = {
        "count": active_templates,
        "status": "ok" if active_templates >= 3 else "warning" if active_templates >= 1 else "critical"
    }

    # Links
    active_links = db.query(CampaignLink).filter(
        CampaignLink.campaign_id == c.id, CampaignLink.active == True  # noqa
    ).count()
    checks["links"] = {
        "count": active_links,
        "status": "ok" if active_links >= 50 else "warning" if active_links >= 10 else "critical"
    }

    # Recipients
    unsent = db.query(CampaignRecipient).filter(
        CampaignRecipient.campaign_id == c.id, CampaignRecipient.sent == False  # noqa
    ).count()
    checks["recipients"] = {
        "count": unsent,
        "status": "ok" if unsent >= 100 else "warning" if unsent >= 1 else "critical"
    }

    # Providers
    checks["providers"] = {
        "list": c.providers or [],
        "status": "ok" if c.providers else "critical"
    }

    # SMS balance (try each configured provider)
    sms_total = 0
    sms_details = []
    try:
        from ..config import load_config
        config = load_config()
        for pname in ["simsms", "grizzly", "5sim"]:
            key = config.get("sms", {}).get(pname, {}).get("api_key", "")
            if key:
                try:
                    from ..modules.birth._helpers import get_sms_provider
                    provider = get_sms_provider(pname)
                    if provider:
                        bal = provider.get_balance()
                        sms_total += bal
                        sms_details.append({"name": pname, "balance": bal})
                except Exception:
                    pass
    except Exception:
        pass

    checks["sms"] = {
        "total_balance": round(sms_total, 2),
        "providers": sms_details,
        "estimated_accounts": int(sms_total / 0.20) if sms_total > 0 else 0,
        "status": "ok" if sms_total >= 5 else "warning" if sms_total > 0 else "critical"
    }

    # Proxies
    from ..models import Proxy, ProxyStatus
    alive_proxies = db.query(Proxy).filter(Proxy.status == ProxyStatus.ACTIVE).count()
    geo_proxies = db.query(Proxy).filter(
        Proxy.status == ProxyStatus.ACTIVE,
        Proxy.geo == c.geo
    ).count() if c.geo else alive_proxies

    checks["proxies"] = {
        "alive": alive_proxies,
        "geo_match": geo_proxies,
        "status": "ok" if alive_proxies >= 10 else "warning" if alive_proxies >= 1 else "critical"
    }

    # Overall
    all_ok = all(v.get("status") != "critical" for v in checks.values())
    checks["ready"] = all_ok

    return checks


# ─── Link Helper (used by Blitz Engine) ───────────────────────────────────────

def get_randomized_link(db: Session, campaign_id: int) -> str | None:
    """Get next ESP link with #hash randomization. Returns None if all exhausted."""
    link = db.query(CampaignLink).filter(
        CampaignLink.campaign_id == campaign_id,
        CampaignLink.active == True,  # noqa
        CampaignLink.use_count < CampaignLink.max_uses
    ).order_by(CampaignLink.use_count.asc()).first()

    if not link:
        return None

    link.use_count += 1
    if link.use_count >= link.max_uses:
        link.active = False

    rand = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
    return f"{link.esp_url}#{rand}"


def get_random_template(db: Session, campaign_id: int) -> CampaignTemplate | None:
    """Get random active template for a campaign."""
    templates = db.query(CampaignTemplate).filter(
        CampaignTemplate.campaign_id == campaign_id,
        CampaignTemplate.active == True  # noqa
    ).all()
    if not templates:
        return None
    t = random.choice(templates)
    t.use_count += 1
    return t


def get_next_recipient(db: Session, campaign_id: int) -> CampaignRecipient | None:
    """Get next unsent recipient."""
    return db.query(CampaignRecipient).filter(
        CampaignRecipient.campaign_id == campaign_id,
        CampaignRecipient.sent == False  # noqa
    ).first()
