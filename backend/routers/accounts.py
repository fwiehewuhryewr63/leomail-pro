"""
Accounts router — full CRUD + bulk operations for account management.
GET   /api/accounts/          — list with pagination, filters, search
GET   /api/accounts/{id}      — single account details
DELETE /api/accounts/{id}     — delete account + unbind proxy
POST  /api/accounts/batch-delete  — bulk delete
POST  /api/accounts/batch-status  — bulk status change
POST  /api/accounts/batch-move    — bulk move to farm
POST  /api/accounts/export        — export selected accounts as text
"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, func
from pydantic import BaseModel
from typing import Optional
from loguru import logger

from ..database import get_db
from ..models import Account, Farm, Proxy, farm_accounts, AccountStatus

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


# ─── Schemas ───

class BatchDeleteRequest(BaseModel):
    ids: list[int]

class BatchStatusRequest(BaseModel):
    ids: list[int]
    status: str  # new, warmed, paused, dead, banned, etc.

class BatchMoveRequest(BaseModel):
    ids: list[int]
    target_farm_id: int

class ExportRequest(BaseModel):
    ids: list[int] | None = None  # None = export all filtered
    format: str = "text"  # text or json
    status: str | None = None
    provider: str | None = None
    farm_id: int | None = None


def _account_to_dict(acc: Account) -> dict:
    """Convert Account model to API response dict."""
    farm_names = [f.name for f in acc.farms] if acc.farms else []
    farm_ids = [f.id for f in acc.farms] if acc.farms else []
    return {
        "id": acc.id,
        "email": acc.email,
        "password": acc.password,
        "provider": acc.provider,
        "status": acc.status,
        "first_name": acc.first_name,
        "last_name": acc.last_name,
        "gender": acc.gender,
        "geo": acc.geo,
        "warmup_day": acc.warmup_day,
        "health_score": acc.health_score,
        "sent_count": acc.total_emails_sent or 0,
        "bounces": acc.bounces or 0,
        "imap_verified": acc.imap_verified,
        "proxy": acc.proxy.to_string() if acc.proxy else None,
        "proxy_id": acc.proxy_id,
        "farm_name": farm_names[0] if farm_names else None,
        "farm_id": farm_ids[0] if farm_ids else None,
        "farm_names": farm_names,
        "created_at": acc.created_at.isoformat() if acc.created_at else None,
        "last_active": acc.last_active.isoformat() if acc.last_active else None,
    }


@router.get("/")
async def list_accounts(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status: Optional[str] = None,
    provider: Optional[str] = None,
    farm_id: Optional[int] = None,
    search: Optional[str] = None,
    sort: Optional[str] = "created_at",
    order: Optional[str] = "desc",
    db: Session = Depends(get_db),
):
    """List accounts with filtering, search, and pagination."""
    query = db.query(Account)

    # Filters
    if status:
        statuses = [s.strip() for s in status.split(",")]
        query = query.filter(Account.status.in_(statuses))
    if provider:
        providers = [p.strip() for p in provider.split(",")]
        query = query.filter(Account.provider.in_(providers))
    if farm_id:
        query = query.join(farm_accounts).filter(farm_accounts.c.farm_id == farm_id)
    if search:
        query = query.filter(Account.email.ilike(f"%{search}%"))

    # Total count for pagination
    total = query.count()

    # Sorting
    sort_col = getattr(Account, sort, Account.created_at)
    query = query.order_by(desc(sort_col) if order == "desc" else asc(sort_col))

    # Pagination
    offset = (page - 1) * page_size
    accounts = query.offset(offset).limit(page_size).all()

    return {
        "accounts": [_account_to_dict(a) for a in accounts],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/{account_id}")
async def get_account(account_id: int, db: Session = Depends(get_db)):
    """Get single account with full details."""
    acc = db.query(Account).filter(Account.id == account_id).first()
    if not acc:
        return {"error": "Account not found"}
    data = _account_to_dict(acc)
    # Extra fields for detail view
    data["recovery_email"] = acc.recovery_email
    data["recovery_phone"] = acc.recovery_phone
    data["birthday"] = acc.birthday.isoformat() if acc.birthday else None
    data["language"] = acc.language
    data["birth_ip"] = acc.birth_ip
    data["user_agent"] = acc.user_agent
    data["warmup_started_at"] = acc.warmup_started_at.isoformat() if acc.warmup_started_at else None
    data["emails_sent_today"] = acc.emails_sent_today or 0
    return data


@router.delete("/{account_id}")
async def delete_account(account_id: int, db: Session = Depends(get_db)):
    """Delete a single account."""
    acc = db.query(Account).filter(Account.id == account_id).first()
    if not acc:
        return {"error": "Account not found"}
    email = acc.email
    # Unbind proxy
    if acc.proxy_id:
        proxy = db.query(Proxy).filter(Proxy.id == acc.proxy_id).first()
        if proxy and proxy.bound_account_id == acc.id:
            proxy.bound_account_id = None
    # Remove from farms
    db.execute(farm_accounts.delete().where(farm_accounts.c.account_id == account_id))
    db.delete(acc)
    db.commit()
    logger.info(f"[Accounts] Deleted: {email}")
    return {"ok": True, "deleted": email}


@router.post("/batch-delete")
async def batch_delete_accounts(req: BatchDeleteRequest, db: Session = Depends(get_db)):
    """Delete multiple accounts by IDs."""
    if not req.ids:
        return {"error": "No IDs provided"}
    accounts = db.query(Account).filter(Account.id.in_(req.ids)).all()
    deleted = []
    for acc in accounts:
        # Unbind proxy
        if acc.proxy_id:
            proxy = db.query(Proxy).filter(Proxy.id == acc.proxy_id).first()
            if proxy and proxy.bound_account_id == acc.id:
                proxy.bound_account_id = None
        deleted.append(acc.email)
        db.execute(farm_accounts.delete().where(farm_accounts.c.account_id == acc.id))
        db.delete(acc)
    db.commit()
    logger.info(f"[Accounts] Batch deleted {len(deleted)} accounts")
    return {"ok": True, "deleted_count": len(deleted)}


@router.post("/batch-status")
async def batch_change_status(req: BatchStatusRequest, db: Session = Depends(get_db)):
    """Change status of multiple accounts."""
    valid_statuses = [s.value for s in AccountStatus]
    if req.status not in valid_statuses:
        return {"error": f"Invalid status: {req.status}. Must be one of: {valid_statuses}"}
    updated = db.query(Account).filter(Account.id.in_(req.ids)).update(
        {Account.status: req.status}, synchronize_session="fetch"
    )
    db.commit()
    logger.info(f"[Accounts] Changed {updated} accounts to status={req.status}")
    return {"ok": True, "updated_count": updated}


@router.post("/batch-move")
async def batch_move_accounts(req: BatchMoveRequest, db: Session = Depends(get_db)):
    """Move accounts to a target farm (removes from all other farms first)."""
    target_farm = db.query(Farm).filter(Farm.id == req.target_farm_id).first()
    if not target_farm:
        return {"error": "Target farm not found"}
    accounts = db.query(Account).filter(Account.id.in_(req.ids)).all()
    moved = 0
    for acc in accounts:
        # Remove from all current farms
        db.execute(farm_accounts.delete().where(farm_accounts.c.account_id == acc.id))
        # Add to target farm
        db.execute(farm_accounts.insert().values(farm_id=req.target_farm_id, account_id=acc.id))
        moved += 1
    db.commit()
    logger.info(f"[Accounts] Moved {moved} accounts to farm '{target_farm.name}'")
    return {"ok": True, "moved_count": moved, "target_farm": target_farm.name}


@router.post("/export")
async def export_accounts(req: ExportRequest, db: Session = Depends(get_db)):
    """Export accounts as email:password text or JSON."""
    if req.ids:
        accounts = db.query(Account).filter(Account.id.in_(req.ids)).all()
    else:
        query = db.query(Account)
        if req.status:
            query = query.filter(Account.status == req.status)
        if req.provider:
            query = query.filter(Account.provider == req.provider)
        if req.farm_id:
            query = query.join(farm_accounts).filter(farm_accounts.c.farm_id == req.farm_id)
        accounts = query.all()

    if req.format == "json":
        return {"accounts": [a.to_export() for a in accounts], "count": len(accounts)}

    # Default: text format email:password
    lines = [f"{a.email}:{a.password}" for a in accounts]
    return PlainTextResponse(
        content="\n".join(lines),
        media_type="text/plain",
        headers={"Content-Disposition": "attachment; filename=accounts_export.txt"},
    )
