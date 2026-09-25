"""entry_value: preserva decimales en snapshots SEC (B19: BPA 7,26 -> 7)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from sec_snapshot_values import entry_value  # noqa: E402


def test_enteros_se_mantienen_como_int():
    assert entry_value(416160000000) == 416160000000
    assert isinstance(entry_value(416160000000), int)
    assert entry_value("98280000000") == 98280000000


def test_fracciones_se_conservan():
    assert entry_value(7.26) == 7.26
    assert isinstance(entry_value(7.26), float)
    assert entry_value(0.0823) == 0.0823
    assert entry_value("6.13") == 6.13


def test_none_y_negativos():
    assert entry_value(None) is None
    assert entry_value(-9447000000) == -9447000000
    assert entry_value(-0.49) == -0.49
