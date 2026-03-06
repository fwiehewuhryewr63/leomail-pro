"""
Leomail v4 - Task Report Generator
Generates a resource consumption report after each task completes.
Combines cost tracking data + thread logs + account stats.
"""
from datetime import datetime
from loguru import logger


class TaskReport:
    """
    Generates post-task completion reports with:
    - SMS usage and costs
    - Captcha usage and costs
    - Proxy usage
    - Account creation stats
    - Cost per account
    """

    def generate(self, task_id: int) -> dict:
        """Generate a comprehensive task completion report."""
        try:
            from ..database import SessionLocal
            from ..models import CostRecord, ThreadLog, Task
            from sqlalchemy import func

            db = SessionLocal()
            try:
                # Task info
                task = db.query(Task).filter(Task.id == task_id).first()
                if not task:
                    return {"error": f"Task {task_id} not found"}

                # Cost breakdown by type
                cost_rows = db.query(
                    CostRecord.resource_type,
                    CostRecord.provider,
                    func.sum(CostRecord.amount).label("total"),
                    func.count().label("count"),
                    func.sum(
                        func.cast(CostRecord.success == True, type_=func.integer if hasattr(func, 'integer') else None)
                    ).label("success_count"),
                ).filter(
                    CostRecord.task_id == task_id,
                ).group_by(
                    CostRecord.resource_type, CostRecord.provider
                ).all()

                # Build cost breakdown
                costs_by_type = {}
                grand_total = 0.0
                for resource_type, provider, total, count, success_count in cost_rows:
                    if resource_type not in costs_by_type:
                        costs_by_type[resource_type] = {
                            "total": 0, "count": 0, "providers": {}
                        }
                    costs_by_type[resource_type]["total"] += total or 0
                    costs_by_type[resource_type]["count"] += count or 0
                    costs_by_type[resource_type]["providers"][provider or "unknown"] = {
                        "total": round(total or 0, 2),
                        "count": count or 0,
                    }
                    grand_total += total or 0

                # Round totals
                for rt in costs_by_type:
                    costs_by_type[rt]["total"] = round(costs_by_type[rt]["total"], 2)

                # SMS-specific: orders vs cancels
                sms_ordered = db.query(CostRecord).filter(
                    CostRecord.task_id == task_id,
                    CostRecord.resource_type == "sms",
                ).count()
                sms_cancelled = db.query(CostRecord).filter(
                    CostRecord.task_id == task_id,
                    CostRecord.resource_type == "sms",
                    CostRecord.success == False,  # noqa: E712
                ).count()
                sms_cost = db.query(func.sum(CostRecord.amount)).filter(
                    CostRecord.task_id == task_id,
                    CostRecord.resource_type == "sms",
                ).scalar() or 0

                # Captcha stats
                captcha_solved = db.query(CostRecord).filter(
                    CostRecord.task_id == task_id,
                    CostRecord.resource_type == "captcha",
                    CostRecord.success == True,  # noqa: E712
                ).count()
                captcha_cost = db.query(func.sum(CostRecord.amount)).filter(
                    CostRecord.task_id == task_id,
                    CostRecord.resource_type == "captcha",
                ).scalar() or 0

                # Thread/account stats
                threads_ok = db.query(ThreadLog).filter(
                    ThreadLog.task_id == task_id,
                    ThreadLog.status == "done",
                ).count()
                threads_err = db.query(ThreadLog).filter(
                    ThreadLog.task_id == task_id,
                    ThreadLog.status.in_(["error", "stopped"]),
                ).count()
                threads_total = threads_ok + threads_err

                # Unique proxies used
                proxies_used = db.query(
                    func.count(func.distinct(ThreadLog.proxy_info))
                ).filter(
                    ThreadLog.task_id == task_id,
                    ThreadLog.proxy_info != None,  # noqa: E711
                ).scalar() or 0

                # Cost per account
                cost_per_account = round(
                    grand_total / threads_ok, 2
                ) if threads_ok > 0 else 0

                # Success rate
                success_rate = round(
                    threads_ok / threads_total * 100, 1
                ) if threads_total > 0 else 0

                report = {
                    "task_id": task_id,
                    "task_type": task.type,
                    "task_status": task.status,
                    "generated_at": datetime.utcnow().isoformat(),

                    # Resource costs
                    "costs": costs_by_type,
                    "grand_total": round(grand_total, 2),
                    "cost_per_account": cost_per_account,

                    # SMS details
                    "sms": {
                        "ordered": sms_ordered,
                        "cancelled": sms_cancelled,
                        "success_rate": round(
                            (sms_ordered - sms_cancelled) / sms_ordered * 100, 1
                        ) if sms_ordered > 0 else 0,
                        "cost": round(sms_cost, 2),
                        "saved_by_cancels": round(sms_cancelled * 0.10, 2),
                    },

                    # Captcha details
                    "captcha": {
                        "solved": captcha_solved,
                        "cost": round(captcha_cost, 2),
                    },

                    # Accounts
                    "accounts": {
                        "created": threads_ok,
                        "failed": threads_err,
                        "total_attempts": threads_total,
                        "success_rate": success_rate,
                    },

                    # Proxies
                    "proxies_used": proxies_used,
                }

                return report

            finally:
                db.close()

        except Exception as e:
            logger.error(f"[TaskReport] Failed to generate report for task {task_id}: {e}")
            return {"error": str(e)}


# Singleton
task_report = TaskReport()
