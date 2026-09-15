"""生成探测变体 + 纯度检查 + 记录清单。

用法：python3 probe/build.py
输出：probe/out/<base>/*.txt 以及 probe/out/manifest.csv

纯度（purity）：消融后目标规则命中数应下降，其他规则不应变化。
purity = 目标变化量 / (目标变化量 + 附带变化量)
纯度低的变体不能用于因果归因，清单里会标出来。
"""
import csv
import difflib
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "engine"))
sys.path.insert(0, str(ROOT))

from diagnose import diagnose          # noqa: E402
from ablations import ABLATIONS        # noqa: E402

BASES = ROOT / "bases"
OUT = ROOT / "out"


def analyse(text):
    r = diagnose(text)
    counts = Counter(f["rule_id"] for f in r["findings"])
    return counts, r


def edited_spans(base, variant):
    """base 中被本次消融删改掉的区间。"""
    sm = difflib.SequenceMatcher(None, base, variant, autojunk=False)
    return [(i1, i2) for tag, i1, i2, _, _ in sm.get_opcodes() if tag in ("delete", "replace")]


def purity(base_rep, var_rep, target, base, variant):
    """纯度 = 目标降幅 / (目标降幅 + 真实附带改动)。

    关键修正：删掉一整句时，句中顺带消失的其他命中**不算附带损伤**——
    那是同一次干预的必然结果，不是失控。只有落在未编辑区域的意外增减才算。
    """
    spans = edited_spans(base, variant)
    def inside(f):
        return any(f["start"] < e and s_ < f["end"] for s_, e in spans)

    bf, vf = base_rep["findings"], var_rep["findings"]
    bc, vc = Counter(f["rule_id"] for f in bf), Counter(f["rule_id"] for f in vf)
    tgt_drop = max(0, bc.get(target, 0) - vc.get(target, 0))

    # 逐规则比较「预期消失数」与「实际消失数」：
    # 落在编辑区内的命中本就该消失，只有超出这个数的才是失控。
    expected_drop = Counter(f["rule_id"] for f in bf if inside(f))
    collateral = 0
    for rule in set(bc) | set(vc):
        if rule == target:
            continue
        actual = bc.get(rule, 0) - vc.get(rule, 0)
        collateral += max(0, actual - expected_drop.get(rule, 0))   # 意外消失
        collateral += max(0, -actual)                               # 意外新增

    if tgt_drop == 0:
        return 0.0, 0, collateral
    return round(tgt_drop / (tgt_drop + collateral), 3), tgt_drop, collateral


def main():
    OUT.mkdir(exist_ok=True)
    rows = []
    bases = sorted(BASES.glob("*.txt"))
    if not bases:
        print(f"没有基准文本。把 AI 生成的中文学术段落放进 {BASES}/ 再运行。")
        return

    for bp in bases:
        text = bp.read_text(encoding="utf-8")
        bdir = OUT / bp.stem
        bdir.mkdir(exist_ok=True)
        bcounts, brep = analyse(text)
        (bdir / "00_base.txt").write_text(text, encoding="utf-8")
        rows.append({"base": bp.stem, "variant": "00_base", "rule_id": "-",
                     "n_changes": 0, "purity": 1.0, "target_drop": 0, "collateral": 0,
                     "n_chars": brep["summary"]["总字数"],
                     "engine_findings": brep["summary"]["检出特征总数"],
                     "detector": "", "score": ""})

        applicable = 0
        for rid, (name, fn) in ABLATIONS.items():
            new, n = fn(text)
            if n == 0 or new.strip() == text.strip():
                continue                      # 该基准文本没有这个特征，跳过
            vcounts, vrep = analyse(new)
            tgt = "V-T1" if rid == "V-T1" else ("V-T2" if rid == "V-T2" else rid)
            if rid == "BURST":
                # 统计型消融不对应任何规则，用句长变异系数的变化来衡量
                cv0 = brep["metrics"]["sent_len_cv"]; cv1 = vrep["metrics"]["sent_len_cv"]
                p, drop, coll = "n/a", f"CV {cv0}→{cv1}", "-"
            else:
                p, drop, coll = purity(brep, vrep, tgt, text, new)
            fname = f"{rid}_{name}.txt".replace("/", "_")
            (bdir / fname).write_text(new, encoding="utf-8")
            rows.append({"base": bp.stem, "variant": fname[:-4], "rule_id": rid,
                         "n_changes": n, "purity": p, "target_drop": drop,
                         "collateral": coll,
                         "n_chars": vrep["summary"]["总字数"],
                         "engine_findings": vrep["summary"]["检出特征总数"],
                         "detector": "", "score": ""})
            applicable += 1

        # 全清变体：效果上界
        allt = text
        for rid, (name, fn) in ABLATIONS.items():
            if rid == "BURST":
                continue
            allt, _ = fn(allt)
        acounts, arep = analyse(allt)
        (bdir / "ZZ_ALL_全部消融.txt").write_text(allt, encoding="utf-8")
        rows.append({"base": bp.stem, "variant": "ZZ_ALL_全部消融", "rule_id": "ALL",
                     "n_changes": -1, "purity": "-", "target_drop": "-", "collateral": "-",
                     "n_chars": arep["summary"]["总字数"],
                     "engine_findings": arep["summary"]["检出特征总数"],
                     "detector": "", "score": ""})
        print(f"{bp.stem}: 基准 {brep['summary']['检出特征总数']} 处特征 → "
              f"{applicable} 个单特征变体 + 全清变体（全清后剩 {arep['summary']['检出特征总数']} 处）")

    mf = OUT / "manifest.csv"
    with mf.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    low = [r for r in rows if isinstance(r["purity"], float) and r["purity"] < 0.6]
    print(f"\n共 {len(rows)} 个变体 → {mf}")
    if low:
        print(f"⚠ 纯度 <0.6 的变体 {len(low)} 个（附带改动过多，因果归因不可靠）：")
        for r in low:
            print(f"    {r['base']}/{r['variant']}  纯度{r['purity']} "
                  f"目标降{r['target_drop']} 附带{r['collateral']}")
    print("\n下一步：把每个 .txt 贴进检测器，把分数填回 manifest.csv 的 score 列"
          "（detector 列写检测器名），然后运行 python3 probe/analyze.py")


if __name__ == "__main__":
    main()
