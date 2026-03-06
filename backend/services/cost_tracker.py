"""
Leomail v4 - Cost Tracker
Tracks every SMS order, captcha solve, and proxy cost.
Provides per-task, per-account, and daily cost summaries.
"""
from datetime import datetime, timedelta
from loguru import logger

# ── In-memory session totals (reset per app restart) ──
_session_costs = {
    "sms": 0.0,
    "captcha": 0.0,
    "proxy": 0.0,
    "sms_orders": 0,
    "sms_cancels": 0,
    "captcha_solves": 0,
}


class CostTracker:
    """
    Records resource costs to DB and maintains session totals.
    Thread-safe: each call creates its own DB session.
    """

    def record_sms(
        self,
        task_id: int = None,
        provider: str = "",
        amount: float = 0.0,
        country: str = "",
        account_email: str = "",
        order_id: str = "",
        success: bool = True,
    ):
        """Record an SMS order cost."""
        _session_costs["sms"] += amount
        _session_costs["sms_orders"] += 1
        if not success:
            _session_costs["sms_cancels"] += 1

        self._save_record(
            task_id=task_id,
            resource_type="sms",
            provider=provider,
            amount=amount,
            country=country,
            account_email=account_email,
            details=f"order_id={order_id}" if order_id else "",
            success=success,
        )

    def record_captcha(
        self,
        task_id: int = None,
        provider: str = "",
        amount: float = 0.0,
        captcha_type: str = "",
        success: bool = True,
    ):
        """Record a captcha solve cost."""
        _session_costs["captcha"] += amount
        _session_costs["captcha_solves"] += 1

        self._save_record(
            task_id=task_id,
            resource_type="captcha",
            provider=provider,
            amount=amount,
            details=f"type={captcha_type}" if captcha_type else "",
            success=success,
        )

    def record_proxy(
        self,
        task_id: int = None,
        provider: str = "",
        amount: float = 0.0,
        account_email: str = "",
    ):
        """Record proxy usage cost (amortized)."""
        _session_costs["proxy"] += amount

        self._save_record(
            task_id=task_id,
            resource_type="proxy",
            provider=provider,
            amount=amount,
            account_email=account_email,
            success=True,
        )

    def _save_record(self, **kwargs):
        """Save a cost record to the database."""
        try:
            from ..database import SessionLocal
            from ..models import CostRecord
            db = SessionLocal()
            try:
                record = CostRecord(**kwargs)
                db.add(record)
                db.commit()
            except Exception as e:
                db.rollback()
                logger.debug(f"[CostTracker] Failed to save record: {e}")
            finally:
                db.close()
        except Exception as e:
            logger.debug(f"[CostTracker] DB error: {e}")

    def get_session_totals(self) -> dict:
        """Get in-memory session cost totals (fast, no DB)."""
        total = _session_costs["sms"] + _session_costs["captcha"] + _session_costs["proxy"]
        return {
            "sms": round(_session_costs["sms"], 2),
            "captcha": round(_session_costs["captcha"], 2),
            "proxy": round(_session_costs["proxy"], 2),
            "total": round(total, 2),
            "sms_orders": _session_costs["sms_orders"],
            "sms_cancels": _session_costs["sms_cancels"],
            "captcha_solves": _session_costs["captcha_solves"],
        }

    def get_task_summary(self, task_id: int) -> dict:
        """Get cost summary for a specific task (from DB)."""
        try:
            from ..database import SessionLocal
            from ..models import CostRecord
            from sqlalchemy import func
            db = SessionLocal()
            try:
                rows = db.query(
                    CostRecord.resource_type,
                    func.sum(CostRecord.amount).label("total"),
                    func.count().label("count"),
                ).filter(
                    CostRecord.task_id == task_id
                ).group_by(CostRecord.resource_type).all()

                result = {}
                grand_total = 0.0
                for resource_type, total, count in rows:
                    result[resource_type] = {
                        "total": round(total or 0, 2),
                        "count": count,
                    }
                    grand_total += total or 0

                # Count successful accounts for this task
                from ..models import ThreadLog
                accounts_created = db.query(ThreadLog).filter(
                    ThreadLog.task_id == task_id,
                    ThreadLog.status == "done",
                ).count()

                result["grand_total"] = round(grand_total, 2)
                result["accounts_created"] = accounts_created
                result["cost_per_account"] = round(
                    grand_total / accounts_created, 2
                ) if accounts_created > 0 else 0

                return result
            finally:
                db.close()
        except Exception as e:
            logger.debug(f"[CostTracker] get_task_summary error: {e}")
            return {}

    def get_today_summary(self) -> dict:
        """Get today's cost summary from DB."""
        try:
            from ..database import SessionLocal
            from ..models import CostRecord
            from sqlalchemy import func
            db = SessionLocal()
            try:
                today_start = datetime.utcnow().replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                rows = db.query(
                    CostRecord.resource_type,
                    func.sum(CostRecord.amount).label("total"),
                    func.count().label("count"),
                ).filter(
                    CostRecord.created_at >= today_start,
                ).group_by(CostRecord.resource_type).all()

                result = {}
                grand_total = 0.0
                for resource_type, total, count in rows:
                    result[resource_type] = {
                        "total": round(total or 0, 2),
                        "count": count,
                    }
                    grand_total += total or 0
                result["grand_total"] = round(grand_total, 2)
                return result
            finally:
                db.close()
        except Exception as e:
            logger.debug(f"[CostTracker] get_today_summary error: {e}")
            return {"grand_total": 0}

    def get_daily_breakdown(self, days: int = 7) -> list:
        """Get per-day cost breakdown for the last N days."""
        try:
            from ..database import SessionLocal
            from ..models import CostRecord
            from sqlalchemy import func
            db = SessionLocal()
            try:
                now = datetime.utcnow()
                result = []
                for i in range(days - 1, -1, -1):
                    day_start = (now - timedelta(days=i)).replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )
                    day_end = day_start + timedelta(days=1)
                    day_label = day_start.strftime("%d %b")

                    total = db.query(func.sum(CostRecord.amount)).filter(
                        CostRecord.created_at >= day_start,
                        CostRecord.created_at < day_end,
                    ).scalar() or 0

                    result.append({
                        "date": day_label,
                        "amount": round(total, 2),
                    })
                return result
            finally:
                db.close()
        except Exception as e:
            logger.debug(f"[CostTracker] get_daily_breakdown error: {e}")
            return []


# Singleton
cost_tracker = CostTracker()
