"""
Leomail v4 — Engine Manager
Singleton that manages 3 independent engines running in parallel:
  1. AUTOREG (birth)  — creates accounts → Farm
  2. WARMUP           — warms up accounts from farms → Ready status
  3. CAMPAIGN (work)  — sends emails using warmed accounts

Each engine has its own thread pool, cancel event, and status tracking.
Shared resources (proxies, accounts DB) use locks to avoid conflicts.
"""
import threading
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
from loguru import logger


class EngineType(str, Enum):
    AUTOREG = "autoreg"
    WARMUP = "warmup"
    CAMPAIGN = "campaign"


class EngineStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"


class EngineState:
    """State tracking for a single engine."""

    def __init__(self, engine_type: EngineType):
        self.type = engine_type
        self.status: EngineStatus = EngineStatus.IDLE
        self.cancel_event = threading.Event()
        self.threads: int = 0
        self.started_at: Optional[datetime] = None
        self.task_id: Optional[int] = None

        # Progress counters
        self.total_target: int = 0
        self.completed: int = 0
        self.failed: int = 0

        # Lock for updating counters
        self._lock = threading.Lock()

    def reset(self):
        """Reset state for new run."""
        self.cancel_event.clear()
        self.completed = 0
        self.failed = 0
        self.total_target = 0
        self.started_at = datetime.now()

    def to_dict(self) -> dict:
        """Serialize for API response."""
        return {
            "type": self.type.value,
            "status": self.status.value,
            "threads": self.threads,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "task_id": self.task_id,
            "total_target": self.total_target,
            "completed": self.completed,
            "failed": self.failed,
            "elapsed_seconds": (datetime.now() - self.started_at).total_seconds() if self.started_at else 0,
        }

    def increment_completed(self):
        with self._lock:
            self.completed += 1

    def increment_failed(self):
        with self._lock:
            self.failed += 1


class EngineManager:
    """
    Singleton manager for all 3 engines.
    Provides shared proxy lock and independent engine lifecycle.
    """
    _instance = None
    _init_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # 3 independent engine states
        self.engines: Dict[EngineType, EngineState] = {
            EngineType.AUTOREG: EngineState(EngineType.AUTOREG),
            EngineType.WARMUP: EngineState(EngineType.WARMUP),
            EngineType.CAMPAIGN: EngineState(EngineType.CAMPAIGN),
        }

        # Shared proxy lock — prevents 2 engines from grabbing the same proxy
        self.proxy_lock = threading.Lock()

        # Global event loop for async engines
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None

        logger.info("[EngineManager] Initialized — 3 engines ready")

    # ── Engine Lifecycle ──

    def get_engine(self, engine_type: EngineType) -> EngineState:
        """Get engine state by type."""
        return self.engines[engine_type]

    def is_running(self, engine_type: EngineType) -> bool:
        """Check if a specific engine is running."""
        return self.engines[engine_type].status == EngineStatus.RUNNING

    def start_engine(self, engine_type: EngineType, threads: int, total_target: int, task_id: int = None):
        """Mark engine as running. Actual work is started by the router."""
        engine = self.engines[engine_type]
        if engine.status == EngineStatus.RUNNING:
            raise RuntimeError(f"Engine {engine_type.value} is already running")

        engine.reset()
        engine.status = EngineStatus.RUNNING
        engine.threads = threads
        engine.total_target = total_target
        engine.task_id = task_id
        logger.info(f"[EngineManager] {engine_type.value} STARTED — {threads} threads, target={total_target}")

    def stop_engine(self, engine_type: EngineType, mode: str = "instant"):
        """Signal engine to stop."""
        engine = self.engines[engine_type]
        if engine.status != EngineStatus.RUNNING:
            logger.warning(f"[EngineManager] {engine_type.value} is not running, cannot stop")
            return

        engine.status = EngineStatus.STOPPING
        engine.cancel_event.set()
        logger.info(f"[EngineManager] {engine_type.value} STOP signal sent (mode={mode})")

    def finish_engine(self, engine_type: EngineType):
        """Mark engine as finished (called when work is done)."""
        engine = self.engines[engine_type]
        engine.status = EngineStatus.IDLE
        logger.info(
            f"[EngineManager] {engine_type.value} FINISHED — "
            f"completed={engine.completed}, failed={engine.failed}"
        )

    # ── Status ──

    def get_status(self) -> Dict[str, Any]:
        """Get status of all 3 engines. Used by frontend."""
        return {
            etype.value: estate.to_dict()
            for etype, estate in self.engines.items()
        }

    def get_running_engines(self) -> list:
        """Get list of currently running engine types."""
        return [
            etype.value for etype, estate in self.engines.items()
            if estate.status == EngineStatus.RUNNING
        ]

    # ── Proxy Lock ──

    def acquire_proxy(self):
        """Acquire proxy lock for safe proxy allocation."""
        self.proxy_lock.acquire()

    def release_proxy(self):
        """Release proxy lock."""
        self.proxy_lock.release()

    # ── Event Loop for async engines ──

    def get_event_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create a shared event loop for async engine tasks."""
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
            self._loop_thread = threading.Thread(
                target=self._run_loop, daemon=True, name="EngineManager-EventLoop"
            )
            self._loop_thread.start()
        return self._loop

    def _run_loop(self):
        """Run the event loop in a background thread."""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def run_async(self, coro):
        """Schedule an async coroutine on the shared event loop."""
        loop = self.get_event_loop()
        return asyncio.run_coroutine_threadsafe(coro, loop)


# ── Module-level singleton access ──
engine_manager = EngineManager()
