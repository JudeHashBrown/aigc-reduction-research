"""读回填好分数的 manifest.csv，算出每个特征的因果效应量，并生成 weights.json。

用法：python3 probe/analyze.py [manifest.csv]

效应量 = 基准分 - 消融后分数（正数 = 去掉该特征能降分）
每处效应 = 效应量 / 改动处数（衡量单位改动的收益，用来排改写优先级）
"""
import csv
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    out = []
    for r in rows:
        if not (r.get("score") or "").strip():
            continue
        try:
            r["score"] = float(r["score"])
        except ValueError:
            continue
        r["n_changes"] = int(r["n_changes"]) if r["n_changes"] not in ("", "-1") else -1
        try:
            r["purity"] = float(r["purity"])
        except (ValueError, TypeError):
            r["purity"] = None
        out.append(r)
    return out


def main(path):
    rows = load(path)
    if not rows:
        print("manifest.csv 里还没有分数。先把变体贴进检测器，把结果填进 score 列。")
        return

    by_det = defaultdict(list)
    for r in rows:
        by_det[r.get("detector") or "未命名"].append(r)

    all_weights = {}
    for det, drows in by_det.items():
        base = {r["base"]: r["score"] for r in drows if r["variant"] == "00_base"}
        if not base:
            print(f"[{det}] 缺少基准分（00_base），跳过")
            continue

        eff = defaultdict(list)     # rule_id -> [效应量]
        per_change = defaultdict(list)
        for r in drows:
            if r["variant"] == "00_base" or r["base"] not in base:
                continue
            delta = base[r["base"]] - r["score"]
            rid = r["rule_id"]
            if rid == "ALL":
                eff["__ALL__"].append(delta)
                continue
            if r["purity"] is not None and r["purity"] < 0.6:
                continue            # 纯度不足，不能用于归因
            eff[rid].append(delta)
            if r["n_changes"] > 0:
                per_change[rid].append(delta / r["n_changes"])

        print("=" * 68)
        print(f"检测器：{det}    基准文本 {len(base)} 篇")
        print("=" * 68)
        if "__ALL__" in eff:
            print(f"全部消融的总降幅：{st.mean(eff['__ALL__']):+.1f} 分"
                  f"（效果上界，n={len(eff['__ALL__'])}）\n")

        ranked = sorted(((k, v) for k, v in eff.items() if k != "__ALL__"),
                        key=lambda kv: st.mean(kv[1]), reverse=True)
        print(f"{'规则':<8}{'平均降幅':>9}{'标准差':>8}{'n':>4}{'每处效应':>10}   判定")
        print("-" * 68)
        for rid, deltas in ranked:
            mean = st.mean(deltas)
            sd = st.stdev(deltas) if len(deltas) > 1 else 0.0
            pc = st.mean(per_change[rid]) if per_change.get(rid) else 0.0
            if mean <= 0.5:
                verdict = "✗ 无效，考虑从引擎移除"
            elif mean < 2:
                verdict = "· 弱"
            elif mean < 5:
                verdict = "✓ 有效"
            else:
                verdict = "★ 强，优先处理"
            print(f"{rid:<8}{mean:>+9.2f}{sd:>8.2f}{len(deltas):>4}{pc:>10.2f}   {verdict}")

        pos = {k: st.mean(v) for k, v in eff.items()
               if k != "__ALL__" and st.mean(v) > 0}
        if pos:
            total = sum(pos.values())
            all_weights[det] = {k: round(v / total * len(pos), 3) for k, v in pos.items()}

        dead = [k for k, v in eff.items() if k != "__ALL__" and st.mean(v) <= 0.5]
        if dead:
            print(f"\n⚠ 以下规则实测无效，说明五份资料的判断在中文检测器上不成立：{', '.join(dead)}")

    if all_weights:
        det = max(all_weights, key=lambda d: len(all_weights[d]))
        # 注意 load() 已经把 score 转成 float 了，这里不能再当字符串用。
        # 第一版写成 (r.get("score") or "").strip() 直接抛 AttributeError——
        # 若不是先用假数据空跑一遍，要等手工提交完 16 次才会撞上。
        rows_det = [r for r in rows if r.get("detector") == det
                    and r.get("score") is not None]
        n_base = sum(1 for r in rows_det if r["variant"] == "00_base")
        n_all = sum(1 for r in rows_det if r["variant"].startswith("ZZ_ALL"))
        thin = [k for k, v in eff.items() if k != "__ALL__" and len(v) < 3]

        # 数据不够就不许写 weights.json。写了的话服务端的 calibrated 标志
        # 会变成 true，界面对用户宣称「已标定」——拿三五个点的样本冒充标定，
        # 比完全不标定更糟：用户会照着一组噪声去改论文。
        if n_base < 5 or n_all < 5:
            wp = ROOT.parent / "engine" / "weights.draft.json"
            reason = f"基准 {n_base} 篇 / 全清 {n_all} 篇，不足 5 篇"
        elif len(thin) > len(eff) // 2:
            wp = ROOT.parent / "engine" / "weights.draft.json"
            reason = f"{len(thin)} 条规则的样本数 <3：{', '.join(sorted(thin)[:6])}"
        else:
            wp = ROOT.parent / "engine" / "weights.json"
            reason = ""

        wp.write_text(json.dumps({
            "detector": det, "rules": all_weights[det],
            "n_bases": n_base, "n_all_variants": n_all,
            "thin_rules": sorted(thin),
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        if reason:
            print(f"\n⚠ 数据不足，只写成草稿 → {wp.name}（{reason}）")
            print("  引擎不会加载草稿，界面也不会显示「已标定」。")
            print("  补齐 P1（8 篇基准 + 8 篇全清）后重跑本脚本即可转正。")
        else:
            print(f"\n已写出标定权重 → {wp}（基于 {det}，{n_base} 篇基准）")
            print("引擎会自动加载：diagnose(text, weights_path='engine/weights.json')")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / "out" / "manifest.csv")
