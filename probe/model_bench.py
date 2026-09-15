"""模型对比基准：用我们自己的诊断引擎评判哪个模型更适合做改写层。

这是本项目独有的能力——五个参考项目都没有打分器，所以它们选模型只能靠感觉。
我们可以直接测。

用法：
    export LLM_BASE_URL=... LLM_API_KEY=...
    python3 probe/model_bench.py claude-sonnet-5 claude-haiku-4-5 gpt-4o-mini

每个模型跑同一批段落，比较六项：
    降幅      AI 加权分下降多少（越高越好）
    采纳率    候选通过护栏且有改进的比例（越高越好）
    编造      因新增数字/文献被判废的次数（越低越好，这是硬指标）
    事实丢失  改写中丢掉的数字/术语/引用数（越低越好）
    新特征    引入了原文没有的 AI 特征种类（越低越好）
    长度偏离  相对原文的长度变化
"""
import os
import statistics as st
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "engine"))
sys.path.insert(0, str(ROOT))

import guard
from diagnose import diagnose
from llm import Client, LLMError
from rewrite import (SEMANTIC, SYS_EN, SYS_ZH, _build_user, _score_candidate,
                     _semantic_findings)
from diagnose import detect_lang, split_paragraphs

# 每 1M token 的美元价格。Claude 数据取自 claude-api skill（2026-06 缓存）。
PRICING = {
    "claude-opus-5":     (5.00, 25.00),
    "claude-opus-4-8":   (5.00, 25.00),
    "claude-sonnet-5":   (2.00, 10.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5":  (1.00,  5.00),
    "claude-fable-5-1": (10.00, 50.00),
}


def est_tokens(s: str) -> int:
    """粗略估算：中文约 1 字 1 token，英文约 4 字符 1 token。"""
    cjk = sum(1 for c in s if '一' <= c <= '鿿')
    return cjk + (len(s) - cjk) // 4


def bench_model(model: str, samples, n_candidates=3):
    client = Client(model=model)
    if not client.configured:
        raise SystemExit("请先设置 LLM_BASE_URL 与 LLM_API_KEY")

    drops, accepts, fabricated, lost, newfeat, ratios = [], [], 0, [], [], []
    tin = tout = 0
    t0 = time.time()

    for text in samples:
        rep = diagnose(text)
        paras = split_paragraphs(text)
        langs = rep.get("para_langs") or [detect_lang(p.text) for p in paras]
        for pi, para in enumerate(paras):
            lang = langs[pi]
            fs = _semantic_findings(rep, pi, lang)
            if not fs:
                continue
            sub = diagnose(para.text)
            sysmsg = SYS_EN if lang == "en" else SYS_ZH
            usermsg = _build_user(para.text, fs, lang)
            try:
                cands = client.complete(sysmsg, usermsg, n=n_candidates)
            except LLMError as e:
                print(f"  ! {model} 调用失败：{e}")
                continue
            tin += est_tokens(sysmsg + usermsg) * len(cands)
            tout += sum(est_tokens(c) for c in cands)

            scored = [_score_candidate(para.text, c, lang, sub, None) for c in cands]
            for s in scored:
                if "编造事实" in s["reason"]:
                    fabricated += 1
            ok = [s for s in scored if s["ok"] and s["score"] > 0]
            accepts.append(1 if ok else 0)
            if ok:
                best = max(ok, key=lambda s: s["score"])
                drops.append(best["weighted_before"] - best["weighted_after"])
                lost.append(best["facts_lost"])
                newfeat.append(len(best["new_rules"]))
                ratios.append(len(best["text"]) / max(1, len(para.text)))

    pin, pout = PRICING.get(model, (None, None))
    cost = (tin / 1e6 * pin + tout / 1e6 * pout) if pin else None
    return {
        "model": model,
        "n": len(accepts),
        "drop": st.mean(drops) if drops else 0.0,
        "accept": st.mean(accepts) if accepts else 0.0,
        "fab": fabricated,
        "lost": st.mean(lost) if lost else 0.0,
        "new": st.mean(newfeat) if newfeat else 0.0,
        "ratio": st.mean(ratios) if ratios else 0.0,
        "cost": cost, "tin": tin, "tout": tout,
        "sec": time.time() - t0,
    }


def main(models):
    sdir = ROOT.parent / "samples"
    samples = [p.read_text(encoding="utf-8") for p in sorted(sdir.glob("*.txt"))
               if "human" not in p.name]
    if not samples:
        raise SystemExit(f"没有测试样本，放几篇 AI 稿进 {sdir}/")
    print(f"样本 {len(samples)} 篇，候选数 3，模型 {len(models)} 个\n")

    rows = [bench_model(m, samples) for m in models]
    print(f"{'模型':<22}{'降幅':>7}{'采纳率':>8}{'编造':>6}{'丢失':>7}"
          f"{'新特征':>8}{'长度比':>8}{'成本$':>9}{'秒':>7}")
    print("-" * 84)
    for r in sorted(rows, key=lambda r: -r["drop"]):
        cost = f"{r['cost']:.4f}" if r["cost"] is not None else "—"
        print(f"{r['model']:<22}{r['drop']:>7.2f}{r['accept']:>8.0%}{r['fab']:>6}"
              f"{r['lost']:>7.2f}{r['new']:>8.2f}{r['ratio']:>8.2f}{cost:>9}{r['sec']:>7.1f}")

    print("\n判读：")
    print("  编造 > 0 是**否决项**——护栏能拦住，但说明该模型不适合做学术改写。")
    print("  事实丢失高 = 改写时把数字和术语弄丢了，比 AI 味更严重。")
    print("  降幅接近但成本差几倍时，选便宜的；本任务是受限改写，不吃模型上限。")
    if any(r["cost"] is None for r in rows):
        print("  部分模型无内置报价，成本列为空；可在 PRICING 里补。")


if __name__ == "__main__":
    args = sys.argv[1:] or ["claude-sonnet-5", "claude-haiku-4-5"]
    main(args)
