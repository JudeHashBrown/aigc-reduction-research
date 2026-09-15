"""确定性修复层（第一层）。纯代码，不经模型。

按段落识别语言，中英各用各的变换集。
毫秒级、可复现、不产生新 token，因此不会反向注入 AI 统计特征。
"""
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "probe"))

from ablations import ABLATIONS, tidy_zh
from ablations_en import ABLATIONS_EN
from diagnose import detect_lang, diagnose

# 与 rewrite.CODE_HANDLED 保持一致。S01 不在此列——
# 代码修法是删掉第三项，属于信息丢失，交给 LLM 层。
#
# 顺序要紧：结构规则必须跑在词表之前。
# 否则「发挥着不可替代的作用」会先被词表删成「发挥着的作用」，
# 结构规则再去匹配就匹配出一堆碎片。
SAFE_ZH = ["S08", "S05", "S07", "S04", "S03", "V-T1", "V-T2", "F01", "F02"]
SAFE_EN = ["S08", "S05", "S07", "S04", "P02", "V-T1", "V-T2", "F01"]


def _tidy_en(text: str) -> str:
    text = re.sub(r'\s+([.,;:!?])', r'\1', text)
    text = re.sub(r'([.,;:])\s*\1+', r'\1', text)
    text = re.sub(r'\s{2,}', ' ', text)
    text = re.sub(r'(^|[.!?]\s+)([a-z])', lambda m: m.group(1) + m.group(2).upper(), text)
    return text.strip()


# 低危规则：孤立出现时属于正常人类写作，不该碰。
# 破折号尤其如此——维基指南自己都在讨论要不要把它降级为「历史指标」，
# 且 2026 年的研究发现 ChatGPT 用破折号反而比职业写手更少。
LOW_SEVERITY_RULES = {"F01", "F04", "S10", "S12"}
NOISE_BUDGET_PER_1K = 3      # 每千字允许保留的低危特征数


def _noise_exempt(text: str) -> set:
    """按噪声预算决定哪些低危规则本次不处理。

    落实 humanizer-zh-academic 的原创洞察：目标不是把 AI 特征清到零。
    清得一点不剩会造成新的均质化异常，而且会伤到作者本来就写对的地方。
    """
    rep = diagnose(text)
    budget = max(1, round(len(text) / 1000 * NOISE_BUDGET_PER_1K))
    counts = {}
    for f in rep["findings"]:
        if f["rule_id"] in LOW_SEVERITY_RULES:
            counts[f["rule_id"]] = counts.get(f["rule_id"], 0) + 1
    total_low = sum(counts.values())
    if total_low <= budget:
        return set(counts)            # 全在预算内，一个都不动
    # 超预算则只放过命中最少的那些，直到总数回到预算内
    exempt, running = set(), total_low
    for rid, n in sorted(counts.items(), key=lambda kv: kv[1]):
        if running - n < budget:
            break
        exempt.add(rid)
        running -= n
    return exempt


def codefix(text: str) -> Tuple[str, List[Dict]]:
    exempt = _noise_exempt(text)
    tally, out_paras = {}, []
    for para in text.split("\n"):
        if not para.strip():
            out_paras.append(para)
            continue
        lang = detect_lang(para)
        table = ABLATIONS_EN if lang == "en" else ABLATIONS
        safe = SAFE_EN if lang == "en" else SAFE_ZH
        cur = para
        touched = False
        for rid in safe:
            if rid not in table or rid in exempt:
                continue
            name, fn = table[rid]
            new, n = fn(cur)
            if n and new.strip() != cur.strip():
                key = (rid, name, lang)
                tally[key] = tally.get(key, 0) + n
                cur = new
                touched = True
        # 没改过的段落一个字符都不碰——收尾规则本身也可能误伤作者原文
        if touched:
            cur = tidy_zh(cur) if lang == "zh" else _tidy_en(cur)
        out_paras.append(cur)

    fixed = "\n".join(out_paras)
    fixed = re.sub(r'[ \t]+\n', '\n', fixed)
    fixed = re.sub(r'\n{3,}', '\n\n', fixed).strip()
    log = [{"rule_id": k[0], "name": k[1], "lang": k[2], "count": v}
           for k, v in sorted(tally.items(), key=lambda kv: -kv[1])]
    if exempt:
        log.append({"rule_id": "—", "lang": "—",
                    "name": f"按噪声预算保留：{'、'.join(sorted(exempt))}", "count": 0})
    return fixed, log
