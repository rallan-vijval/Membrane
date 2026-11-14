"""Bounded best-effort metadata-only LangSmith export."""
from contextlib import contextmanager
from datetime import datetime, timezone
from queue import Queue, Full
from threading import Thread
from uuid import uuid4
ALLOWED = {"candidate_id", "run_id", "case_id", "execution_id", "version_id", "fixture_id", "status", "attempted_calls", "error_code"}
def safe(values):
    return {k: v for k, v in (values or {}).items() if k in ALLOWED and isinstance(v, (str, int, bool, float)) and len(str(v)) <= 128}
class LangSmithTracer:
    def __init__(self, api_key):
        from langsmith import Client
        from urllib3.util.retry import Retry
        self.client = Client(api_key=api_key, auto_batch_tracing=False, timeout_ms=2000, retry_config=Retry(total=0), hide_inputs=True, hide_outputs=True)
        self.queue = Queue(maxsize=128)
        Thread(target=self._send, daemon=True, name="membrane-traces").start()
    def _send(self):
        while True:
            payload = self.queue.get()
            try:
                self.client.create_run(**payload)
            except Exception:
                pass
            finally:
                self.queue.task_done()
    @contextmanager
    def span(self, name, metadata=None):
        class Handle:
            trace_url = None
            outputs = {}
            def set_outputs(self, outputs):
                self.outputs = safe(outputs)
        handle = Handle()
        start = datetime.now(timezone.utc)
        try:
            yield handle
        finally:
            payload = dict(id=uuid4(), name=name[:80], run_type="chain", inputs={}, outputs={}, start_time=start, end_time=datetime.now(timezone.utc), extra={"metadata": {**safe(metadata), **handle.outputs}})
            try:
                self.queue.put_nowait(payload)
            except Full:
                pass
