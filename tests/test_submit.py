"""submit.py 的两个数据完整性不变量。

这两条都是实测中真的丢过数据才补的：
  1. run_range 当初没有数字校验，把粘错窗口的 shell 命令写进了 score 列
  2. run_range 当初每轮从空表重写 CSV，中途 Ctrl+C 就抹掉上一轮填好的行
"""
import csv
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "probe"))
from submit import _num, _flush


def test_num_rejects_non_numbers():
    for bad in ["cd ~/Documents/AI去重",
                "python3 probe/submit.py --detector 朱雀 --tactics",
                "", "  ", "abc", "百分之八十", "101", "-3", "1e400"]:
        assert _num(bad) is None, f"{bad!r} 不该被当成分数"


def test_num_accepts_real_scores():
    assert _num("0") == 0.0
    assert _num("100") == 100.0
    assert _num("32.25") == 32.25
    assert _num(" 87% ") == 87.0


def test_flush_keeps_rows_not_touched_this_run():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        files = [td / f"{n}.txt" for n in ("A", "B", "C")]
        for f in files:
            f.write_text("x", encoding="utf-8")
        csv_path = td / "out.csv"

        done = {"A": {"item": "A", "detector": "朱雀", "score": "0", "n_chars": 1}}
        _flush(csv_path, files, done)
        done["C"] = {"item": "C", "detector": "朱雀", "score": "50", "n_chars": 1}
        _flush(csv_path, files, done)

        rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))
        assert [r["item"] for r in rows] == ["A", "C"], "行序应跟文件序，且 A 不能丢"
        assert rows[0]["score"] == "0"


def test_zero_is_not_treated_as_missing():
    """0 分是本项目目前唯一的有效发现，绝不能被「空值」逻辑吞掉。"""
    assert _num("0") is not None
    assert _num("0") == 0.0
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        f = td / "H1.txt"; f.write_text("x", encoding="utf-8")
        csv_path = td / "out.csv"
        _flush(csv_path, [f], {"H1": {"item": "H1", "detector": "朱雀",
                                      "score": "0", "n_chars": 1}})
        rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))
        assert rows and rows[0]["score"] == "0"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"{len(fns)} passed")
