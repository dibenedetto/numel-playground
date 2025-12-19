# utils

import os


from   datetime  import datetime
from   typing    import Optional


def log_print(*args, **kwargs) -> None:
	print("[log]", *args, **kwargs)


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


def get_time_str() -> str:
	now = datetime.now()
	res = now.strftime("%Y-%m-%d %H:%M:%S")
	return res
