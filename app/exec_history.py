# exec_history.py — Persistent execution history store
#
# Stores a capped ring-buffer of past workflow execution results.
# Each record has: execution_id, workflow_name, timestamp, status, inputs, outputs, duration_ms, error

import json
import os
from collections import deque
from datetime    import datetime
from typing      import Any, Dict, List, Optional

from pydantic    import BaseModel, Field


_HISTORY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exec_history.json")
_MAX_RECORDS  = 500   # rolling cap


class ExecRecord(BaseModel):
    execution_id   : str
    workflow_name  : str            = ""
    timestamp      : str            = Field(default_factory=lambda: datetime.now().isoformat())
    status         : str            = "unknown"   # completed / failed / cancelled
    duration_ms    : Optional[int]  = None
    inputs         : Optional[Any]  = None
    outputs        : Optional[Any]  = None
    error          : Optional[str]  = None


class ExecHistoryManager:
    def __init__(self, path: str = _HISTORY_PATH, max_records: int = _MAX_RECORDS):
        self._path        = path
        self._max_records = max_records
        self._records     : deque[ExecRecord] = deque(maxlen=max_records)
        self._load()

    # ── persistence ────────────────────────────────────────────────

    def _load(self):
        if os.path.exists(self._path):
            try:
                with open(self._path, "r") as f:
                    data = json.load(f)
                for r in data:
                    self._records.append(ExecRecord(**r))
            except Exception:
                pass

    def _save(self):
        try:
            with open(self._path, "w") as f:
                json.dump([r.model_dump() for r in self._records], f, indent=2)
        except Exception:
            pass

    # ── public API ─────────────────────────────────────────────────

    def record(self, **kwargs):
        """Add a new execution record."""
        rec = ExecRecord(**kwargs)
        self._records.append(rec)
        self._save()
        return rec

    def list(self, workflow_name: str = None, limit: int = 100, offset: int = 0) -> List[dict]:
        """Return records newest-first, optionally filtered by workflow_name."""
        items = list(reversed(self._records))
        if workflow_name:
            items = [r for r in items if r.workflow_name == workflow_name]
        return [r.model_dump() for r in items[offset : offset + limit]]

    def get(self, execution_id: str) -> Optional[dict]:
        for r in reversed(self._records):
            if r.execution_id == execution_id:
                return r.model_dump()
        return None

    def clear(self, workflow_name: str = None):
        if workflow_name:
            self._records = deque(
                (r for r in self._records if r.workflow_name != workflow_name),
                maxlen=self._max_records
            )
        else:
            self._records.clear()
        self._save()
