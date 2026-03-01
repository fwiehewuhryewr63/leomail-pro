"""
Leomail v3 - Resource Calculator
Accurate RAM estimates for browser-based (Playwright) operations.
"""
import psutil
from loguru import logger

# RAM usage per concurrent browser context (Playwright/Chromium)
MEMORY_PER_THREAD = {
    "birth": 300,     # Full browser + captcha solving = heavy
    "warmup": 250,    # Browser + compose/read = moderate
    "work": 200,      # Browser + compose/send = lighter (less interaction)
}

# Minimum free RAM to keep (MB)
RAM_RESERVE_MB = 2048  # Keep 2GB free for OS + other processes

# CPU: max threads per core ratio
CPU_RATIO = {
    "birth": 2,       # CPU-light (waiting for pages)
    "warmup": 3,      # Even lighter
    "work": 4,        # Mostly I/O bound
}


class ResourceCalculator:
    """Calculate optimal thread counts based on system resources."""

    @staticmethod
    def get_system_resources() -> dict:
        mem = psutil.virtual_memory()
        cpu_count = psutil.cpu_count(logical=True) or 4
        disk = psutil.disk_usage('/')
        return {
            "ram_total_mb": round(mem.total / 1024 / 1024),
            "ram_available_mb": round(mem.available / 1024 / 1024),
            "ram_used_pct": mem.percent,
            "cpu_count": cpu_count,
            "cpu_percent": psutil.cpu_percent(interval=0.5),
            "disk_total_gb": round(disk.total / 1024 / 1024 / 1024, 1),
            "disk_free_gb": round(disk.free / 1024 / 1024 / 1024, 1),
        }

    @staticmethod
    def get_max_threads(task_type: str, available_proxies: int = 999, active_threads: int = 0) -> dict:
        """
        Calculate maximum recommended threads.
        Returns: {recommended, max_by_ram, max_by_cpu, max_by_proxy, limiting_factor}
        """
        mem = psutil.virtual_memory()
        available_mb = (mem.available / 1024 / 1024) - RAM_RESERVE_MB
        if available_mb < 0:
            available_mb = 0

        mem_per = MEMORY_PER_THREAD.get(task_type, 250)
        max_by_ram = max(1, int(available_mb / mem_per)) - active_threads

        cpu_count = psutil.cpu_count(logical=True) or 4
        ratio = CPU_RATIO.get(task_type, 3)
        max_by_cpu = (cpu_count * ratio) - active_threads

        max_by_proxy = available_proxies - active_threads

        recommended = max(1, min(max_by_ram, max_by_cpu, max_by_proxy))

        # Determine limiting factor
        if recommended == max_by_ram:
            factor = "RAM"
        elif recommended == max_by_cpu:
            factor = "CPU"
        else:
            factor = "Proxies"

        return {
            "recommended": recommended,
            "max_by_ram": max(1, max_by_ram),
            "max_by_cpu": max(1, max_by_cpu),
            "max_by_proxy": max(0, max_by_proxy),
            "limiting_factor": factor,
            "ram_per_thread_mb": mem_per,
        }

    @staticmethod
    def get_health_status() -> dict:
        res = ResourceCalculator.get_system_resources()
        # Traffic light status
        if res["ram_used_pct"] > 90 or res["cpu_percent"] > 90:
            status = "critical"
        elif res["ram_used_pct"] > 75 or res["cpu_percent"] > 75:
            status = "warning"
        else:
            status = "healthy"

        return {
            "status": status,
            **res,
            "max_birth_threads": ResourceCalculator.get_max_threads("birth")["recommended"],
            "max_warmup_threads": ResourceCalculator.get_max_threads("warmup")["recommended"],
            "max_work_threads": ResourceCalculator.get_max_threads("work")["recommended"],
        }
