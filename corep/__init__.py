"""Basel III COREP reporting: own funds (C 01.00-C 03.00) and leverage ratio (C 47.00) for a synthetic EU bank."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CONFIG = ROOT / "config"
SQL = ROOT / "sql"
TAXONOMY = ROOT / "taxonomy"
OUT = ROOT / "out"

# A cell of a COREP template: (template, row, column), e.g. ("C_47.00", "0290", "0010").
Cell = tuple[str, str, str]
