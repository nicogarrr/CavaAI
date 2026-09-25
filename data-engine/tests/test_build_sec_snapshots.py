"""_entry_value: preserva decimales en snapshots SEC (B19: BPA 7,26 -> 7)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from build_sec_snapshots import _entry_value  # noqa: E402


def test_enteros_se_mantienen_como_int():
    assert _entry_value(416160000000) == 416160000000
    assert isinstance(_entry_value(416160000000), int)
    assert _entry_value("98280000000") == 98280000000


def test_fracciones_se_conservan():
    assert _entry_value(7.26) == 7.26
    assert isinstance(_entry_value(7.26), float)
    assert _entry_value(0.0823) == 0.0823
    assert _entry_value("6.13") == 6.13


def test_none_y_negativos():
    assert _entry_value(None) is None
    assert _entry_value(-9447000000) == -9447000000
    assert _entry_value(-0.49) == -0.49
