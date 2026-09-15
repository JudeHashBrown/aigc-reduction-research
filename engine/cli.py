"""命令行诊断：python3 engine/cli.py <文件|-> [--json]"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from diagnose import diagnose

SEV = {"high": "🔴", "medium": "🟡", "low": "🟢"}
LVL = {"high": "🔴高风险", "medium": "🟡中风险", "low": "🟢低风险"}


def report(text: str) -> str:
    r = diagnose(text)
    L = []
    s = r["summary"]
    L.append("=" * 62)
    L.append(f"诊断报告  {s['总字数']} 字 / {s['段落数']} 段 / {s['句数']} 句")
    L.append("=" * 62)
    L.append(f"\n检出 AI 特征 {s['检出特征总数']} 处："
             f"🔴{s['高风险']}  🟡{s['中风险']}  🟢{s['低风险']}")
    L.append(f"高风险段落 {s['高风险段落']} 个；硬约束违反 {s['硬约束违反']} 项")

    if r["hard_limit_violations"]:
        L.append("\n【硬约束违反】命中即需修复")
        for v in r["hard_limit_violations"]:
            where = f"第{v['para']}段" if "para" in v else "全文"
            L.append(f"  ✗ {where}：{v['desc']}（实际 {v['actual']}，上限 {v['limit']}）")

    if r["metric_flags"]:
        L.append("\n【统计指标落入 AI 可疑区间】")
        for f in r["metric_flags"]:
            L.append(f"  · {f['desc']}：实测 {f['value']}，{f['reference']}")

    L.append("\n【逐段诊断】")
    for p in r["paragraphs"]:
        L.append(f"\n第{p['index']+1}段 {LVL[p['level']]}"
                 f"（命中 {p['raw_score']} 类特征，加权 {p['weighted_score']}）")
        L.append(f"  「{p['preview']}…」")
        pf = [f for f in r["findings"] if f["para_index"] == p["index"]]
        for f in pf:
            L.append(f"    {SEV[f['severity']]} [{f['rule_id']}] {f['name']}"
                     f" → 「{f['matched']}」")
            L.append(f"        {f['explain']}")

    doc = [f for f in r["findings"] if f["para_index"] == -1]
    if doc:
        L.append("\n【格式层】")
        for f in doc:
            L.append(f"  {SEV[f['severity']]} [{f['rule_id']}] {f['name']} → 「{f['matched'][:30]}」")

    m = r["metrics"]
    L.append("\n【统计明细】")
    L.append(f"  句长 均值{m['sent_len_mean']} 变异系数{m['sent_len_cv']}"
             f" | 实词密度{m['content_ratio']} | TTR {m['ttr']}")
    L.append(f"  具体性：数字密度{m['digit_density']}/百字"
             f" 专名密度{m['proper_density']}/百字")
    L.append(f"  模板化：4-gram重复{m['ngram_repeat']} 段首雷同{m['para_head_repeat']}")
    return "\n".join(L)


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "-"
    text = sys.stdin.read() if src == "-" else Path(src).read_text(encoding="utf-8")
    if "--json" in sys.argv:
        print(json.dumps(diagnose(text), ensure_ascii=False, indent=2))
    else:
        print(report(text))
