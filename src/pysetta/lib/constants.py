import re

CONFIG_DIR_NAME = ".pysetta"
CONFIG_FILE_NAME = "pysetta.yaml"
TRANSLATION_SUFFIX = ".yaml"

TRANSLATABLE = re.compile(r"<\$(?P<inner_text>.*?)\$>")
LITERAL = re.compile(r"<#(?P<inner_text>.*?)#>")
MARKED = re.compile(r"<@(?P<inner_text>.*?)@>")
COMBINED = re.compile(r"<(?P<symbol>[@$#])(?P<inner_text>.*?)\1>")
