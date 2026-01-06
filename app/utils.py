# utils

import json
import os


from   datetime                import datetime, timezone
from   typing                  import Optional
from   fastapi                 import FastAPI
from   fastapi.middleware.cors import CORSMiddleware


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


def log_print(*args, **kwargs) -> None:
	ts = get_now_str()
	print(f"[log {ts}]", *args, **kwargs)


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
