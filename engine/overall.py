"""整体评估。

产品设计里定死的一条：**不报 AI 率百分比**。
不是因为做不出一个数字，而是因为那个数字必然和知网/维普对不上。
用户看到我们说 40%、知网给 70%，他会永久性地不再信任这个工具——
一次失准毁掉的信任，靠后面多少次准确都补不回来。

但"没有整体判断"也是坏体验。所以这里给的是**可核对的观测量**，
并且明确标注每个量的依据有多硬：

- 材料密度：有两套独立语料支持方向（lieflat 283 万汉字 + 本项目 8 篇基准），
  是目前最可信的一项。
- 句式特征数：**不能当分数用**。本项目的人类对照样本特征密度 3.28/千字，
  反而高于真实 AI 输出的 2.49/千字。这个反直觉结果必须如实告诉用户，
  否则他会把"检出 12 处"误读成"AI 率高"。
"""
import re
from typing import Dict, List

# 参照值。来源写在字段里，界面直接展示——用户有权知道这些数字哪来的。
REF = {
    "digit_per_1k": {
        "human": 17.92, "ai": 6.34,
        "src": "lieflat-less-ai-tone 对照实验，人类 329 篇 164.8 万汉字 / AI 300 篇 117.9 万汉字",
    },
}

_NUM = re.compile(r'\d+(?:[.,]\d+)*\s*%?|[pP]\s*[<>=]\s*0?\.\d+')
_CJK = re.compile(r'[一-鿿]')


def assess(text: str, findings: List[Dict]) -> Dict:
    # 分母：中文按汉字数，英文按词数折算成汉字当量（一个英文词约合 1.6 个汉字的信息量）。
    # 不能用 \b\w+\b 统计中文——\w 在 Python 里包含 CJK，而 \b 只在
    # 中英交界处成立，整段中文会被算成两三个「词」，密度虚高几百倍。
    n_cjk = len(_CJK.findall(text))
    n_word = len(re.findall(r'[A-Za-z]+', text))
    n_unit = max(1.0, float(n_cjk) if n_cjk >= n_word else n_word * 1.6)
    per1k = lambda x: round(x / n_unit * 1000, 2)      # noqa: E731

    digits = len(_NUM.findall(text))
    dd = per1k(digits)

    by_handling = {"code": 0, "llm": 0, "report": 0}
    for f in findings:
        h = f.get("handling")
        if h in by_handling:
            by_handling[h] += 1

    h_ref, a_ref = REF["digit_per_1k"]["human"], REF["digit_per_1k"]["ai"]
    if dd >= h_ref:
        band, verdict = "good", "材料密度达到人类论文的参照水平。"
    elif dd >= a_ref:
        band, verdict = "mid", "材料密度介于 AI 生成与人类论文之间，仍有提升空间。"
    else:
        band, verdict = "low", "材料密度低于 AI 生成文本的平均水平——全文几乎没有具体数字。"

    # 短文本的密度不稳定：一句话里有没有数字，会让密度在 0 和 50 之间跳。
    # 与其给一个会误导人的数字，不如标出来。
    reliable = n_unit >= 300

    return {
        "n_chars": len(text),
        "n_unit": int(n_unit),
        "reliable": reliable,
        "unreliable_note": ("" if reliable else
                            f"全文只有约 {int(n_unit)} 字，密度类指标在这个长度上"
                            f"波动很大，仅供参考。建议整篇文档一起看。"),
        "digit_density_per_1k": dd,
        "digit_ref": REF["digit_per_1k"],
        "band": band,
        "verdict": verdict,
        "feature_per_1k": per1k(len([f for f in findings
                                     if f.get("handling") != "report"])),
        "by_handling": by_handling,
        "total_findings": len(findings),
        # 这两句必须跟着数据一起下发，不能只放在界面文案里——
        # 换个前端就丢了，而它们是这个产品不骗人的底线。
        "disclaimer": (
            "本工具不给 AI 率百分比。任何百分比都无法预测知网、维普会给你多少分，"
            "报一个对不上的数字只会让你做出错误判断。"
            "上面是可以自己核对的观测量，不是分数。"),
        "feature_caveat": (
            "特征数不能当分数读。本项目的人类对照样本句式特征密度是 3.28/千字，"
            "反而高于真实 AI 输出的 2.49/千字——句式特征在我们现有的语料上"
            "区分不出人机。真正拉开差距的是材料密度。"),
    }
