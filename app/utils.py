# utils

from collections import deque
import json
import os
import sys
from threading import Lock


from   datetime                import datetime, timezone
from   typing                  import Optional
from   fastapi                 import FastAPI
from   fastapi.middleware.cors import CORSMiddleware


_RECENT_LOG_MAX_ENTRIES = 400
_RECENT_LOGS = deque(maxlen=_RECENT_LOG_MAX_ENTRIES)
_RECENT_LOGS_LOCK = Lock()


def get_now() -> datetime:
	now = datetime.now(timezone.utc)
	return now


def get_now_str() -> str:
	now = get_now()
	res = now.strftime("%Y-%m-%d--%H:%M:%S")
	return res


def get_timestamp() -> float:
	ts = get_now().timestamp()
	return ts


def get_timestamp_str() -> float:
	ts = str(get_timestamp()).replace(".", "_").replace(",", "_")
	return ts


def clear_recent_logs() -> None:
	with _RECENT_LOGS_LOCK:
		_RECENT_LOGS.clear()


def get_recent_logs(limit: int = 100) -> list[dict]:
	max_items = max(1, int(limit or 100))
	with _RECENT_LOGS_LOCK:
		items = list(_RECENT_LOGS)[-max_items:]
	return [dict(item) for item in items]


def log_print(*args, **kwargs) -> None:
	ts = get_now_str()
	stream = kwargs.pop("file", sys.stdout)
	sep    = kwargs.pop("sep", " ")
	end    = kwargs.pop("end", "\n")
	flush  = kwargs.pop("flush", False)
	parts  = [f"[log {ts}]", *(str(arg) for arg in args)]
	text   = sep.join(parts)
	stream_name = "stderr" if stream is sys.stderr else "stdout"
	with _RECENT_LOGS_LOCK:
		_RECENT_LOGS.append({
			"timestamp": ts,
			"stream": stream_name,
			"text": text,
		})
	try:
		print(text, file=stream, end=end, flush=flush, **kwargs)
	except UnicodeEncodeError:
		encoding = getattr(stream, "encoding", None) or "utf-8"
		safe_text = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
		print(safe_text, file=stream, end=end, flush=flush, **kwargs)


def seed_everything(seed: Optional[int] = None) -> None:
	if not isinstance(seed, int):
		seed = int(datetime.now()) % (2**32)

	os.environ['PYTHONHASHSEED'] = str(seed)

	try:
		import numpy
		numpy.random.seed(seed)
	except:
		pass

	try:
		import torch
		torch .manual_seed(seed)
		torch .cuda.manual_seed(seed)
		torch .cuda.manual_seed_all(seed)
		torch .backends.cudnn.deterministic = True
	except:
		pass


def add_middleware(app: FastAPI) -> None:
	app.add_middleware(
		CORSMiddleware,
		allow_credentials = False,
		allow_headers     = ["*"],
		allow_methods     = ["*"],
		allow_origins     = ["*"],
	)


def serialize_result(result):
	if result is None:
		return None
	try:
		json.dumps(result)
		return result
	except (TypeError, ValueError):
		return str(result)
