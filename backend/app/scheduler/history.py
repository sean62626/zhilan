"""
任务执行历史追踪器

内存单例 + JSON 文件持久化，最多保留 100 条记录。
重启不丢失。
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

EXPORTS_DIR = Path(__file__).parent.parent.parent / "exports"
HISTORY_FILE = EXPORTS_DIR / "job_history.json"
MAX_RECORDS = 100


class JobRun:
    """单次任务执行记录"""

    def __init__(self, job_id: str):
        self.execution_id = uuid.uuid4().hex[:8]
        self.job_id = job_id
        self.started_at = datetime.now(timezone.utc)
        self.finished_at: datetime | None = None
        self.success: bool | None = None
        self.error: str | None = None
        self.result: dict | None = None

    @property
    def duration_ms(self) -> int:
        if self.finished_at is None:
            return int((datetime.now(timezone.utc) - self.started_at).total_seconds() * 1000)
        return int((self.finished_at - self.started_at).total_seconds() * 1000)

    def mark_success(self, result: dict | None = None):
        self.finished_at = datetime.now(timezone.utc)
        self.success = True
        self.result = result

    def mark_failure(self, error: str):
        self.finished_at = datetime.now(timezone.utc)
        self.success = False
        self.error = error

    def to_dict(self) -> dict:
        return {
            "execution_id": self.execution_id,
            "job_id": self.job_id,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "result": self.result,
        }

    @staticmethod
    def from_dict(data: dict) -> "JobRun":
        run = JobRun(job_id=data["job_id"])
        run.execution_id = data["execution_id"]
        run.started_at = datetime.fromisoformat(data["started_at"])
        if data.get("finished_at"):
            run.finished_at = datetime.fromisoformat(data["finished_at"])
        run.success = data.get("success")
        run.error = data.get("error")
        run.result = data.get("result")
        return run


class JobHistoryTracker:
    """任务执行历史追踪器 — 全局单例"""

    def __init__(self):
        self._history: dict[str, list[JobRun]] = {}
        self._load()

    # ========== 持久化 ==========

    def _load(self):
        """从 JSON 文件加载历史记录"""
        try:
            if HISTORY_FILE.exists():
                raw = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
                for job_id, runs in raw.items():
                    self._history[job_id] = [JobRun.from_dict(r) for r in runs]
                logger.info("[history] 已加载 %d 个任务的历史记录", sum(len(v) for v in self._history.values()))
        except Exception as e:
            logger.warning("[history] 加载历史记录失败: %s", e)
            self._history = {}

    def _save(self):
        """保存历史记录到 JSON 文件"""
        try:
            EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
            data = {job_id: [r.to_dict() for r in runs] for job_id, runs in self._history.items()}
            HISTORY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("[history] 保存历史记录失败: %s", e)

    # ========== 记录 ==========

    def start(self, job_id: str) -> JobRun:
        """开始一次任务执行，返回执行记录"""
        run = JobRun(job_id)
        if job_id not in self._history:
            self._history[job_id] = []
        self._history[job_id].insert(0, run)
        logger.info("[history] 任务开始: %s #%s", job_id, run.execution_id)
        return run

    def finish(self, run: JobRun, success: bool, error: str | None = None, result: dict | None = None):
        """完成一次任务执行"""
        if success:
            run.mark_success(result)
            logger.info("[history] 任务成功: %s #%s (耗时 %dms)", run.job_id, run.execution_id, run.duration_ms)
        else:
            run.mark_failure(error or "未知错误")
            logger.warning("[history] 任务失败: %s #%s — %s", run.job_id, run.execution_id, run.error)

        # 裁剪到 MAX_RECORDS
        if len(self._history.get(run.job_id, [])) > MAX_RECORDS:
            self._history[run.job_id] = self._history[run.job_id][:MAX_RECORDS]

        self._save()

    # ========== 查询 ==========

    def get_history(self, job_id: str | None = None, limit: int = 20) -> list[dict]:
        """查询任务执行历史"""
        if job_id:
            runs = self._history.get(job_id, [])
        else:
            runs = []
            for rlist in self._history.values():
                runs.extend(rlist)
            runs.sort(key=lambda r: r.started_at, reverse=True)

        return [r.to_dict() for r in runs[:limit]]

    def get_stats(self) -> dict:
        """获取整体统计数据"""
        all_runs = []
        for runs in self._history.values():
            all_runs.extend(runs)

        total = len(all_runs)
        if total == 0:
            return {"total_runs": 0, "success_rate": 0, "avg_duration_ms": 0}

        succeeded = sum(1 for r in all_runs if r.success is True)
        durations = [r.duration_ms for r in all_runs]

        return {
            "total_runs": total,
            "success_count": succeeded,
            "failure_count": total - succeeded,
            "success_rate": round(succeeded / total * 100, 1),
            "avg_duration_ms": round(sum(durations) / len(durations)),
        }


# 全局单例
_history_tracker: JobHistoryTracker | None = None


def get_history_tracker() -> JobHistoryTracker:
    """获取历史追踪器单例"""
    global _history_tracker
    if _history_tracker is None:
        _history_tracker = JobHistoryTracker()
    return _history_tracker
