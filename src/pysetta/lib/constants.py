import os
import re
from pathlib import Path

CONFIG_DIR_NAME = ".pysetta"
CONFIG_FILE_NAME = "pysetta.yaml"
CACHE_FILE_NAME = ".cache.yaml"
TRANSLATION_SUFFIX = ".yaml"
DEV_NULL = Path(os.devnull)
LITERAL = re.compile(r"[&$]{(?P<inner_text>.*?)}")
