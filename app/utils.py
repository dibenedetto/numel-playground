# utils

import os


from   datetime                import datetime
from   typing                  import Optional
from   fastapi                 import FastAPI
from   fastapi.middleware.cors import CORSMiddleware


def get_time_str() -> str:
	now = datetime.now()
	res = now.strftime("%Y-%m-%d %H:%M:%S")
	return res


def log_print(*args, **kwargs) -> None:
	ts = get_time_str()
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
