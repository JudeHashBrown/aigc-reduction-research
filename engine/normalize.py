"""输入归一化：清掉隐藏字符，并识别繁体。

为什么必须做在诊断之前：
零宽字符会让**全部规则失效**。「研究​表明」不匹配「研究表明」，
一个看不见的字符就能让引擎把满是 AI 特征的文本报成「干净」。

这不是理论风险。一部分「降 AI 率」工具的做法就是往文本里插零宽字符，
用户拿那种文本过来，我们会告诉他没问题——而知网、Turnitin 都会把
隐藏字符判定为篡改，后果比原来的 AI 率更严重。

所以这里不只是清掉，还要**告诉用户清掉了什么**。
"""
import re
import unicodedata
from typing import Dict, Tuple

# 零宽与格式控制字符：肉眼不可见，但会打断所有正则匹配
_INVISIBLE = (
    "​‌‍⁠﻿"      # 零宽空格/非连接/连接/单词连接符/BOM
    "­"                                # 软连字符
    "᠎"                                # 蒙文元音分隔符
    "‪‫‬‭‮"        # 双向控制
    "⁦⁧⁨⁩"              # 双向隔离
)
_INVISIBLE_RE = re.compile(f"[{_INVISIBLE}]")
# 变体选择符
_VARIATION_RE = re.compile(r"[︀-️]")
# 其余 C0/C1 控制字符（保留 \t \n \r）
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
# 非常规空白 → 普通空格（全角空格保留，中文排版里是有意的）
_ODD_SPACE_RE = re.compile(r"[ -   ]")

# 仅在繁体中使用、简体几乎不出现的常用字。命中若干个即判为繁体。
_TRAD_MARKERS = set("這說對於個們時來後會學國發經產業點麼樣實現過導"
                    "應該當開關頭萬與觀係響價證論證書認識義議標準"
                    "處據隨營歸雙擊參態豐執顯錯測驗總結構檢驗")


def looks_traditional(text: str, threshold: int = 3) -> bool:
    """是否像繁体中文。阈值取 3 个不同标记字，避免个别异体字误判。"""
    return len(_TRAD_MARKERS & set(text)) >= threshold


def normalize_text(text: str) -> Tuple[str, Dict]:
    """归一化并返回改动报告。

    返回 (清理后的文本, 报告)。报告里的项都要展示给用户——
    「我替你删掉了 37 个看不见的字符」本身就是有价值的信息。
    """
    report: Dict = {"invisible": 0, "variation": 0, "control": 0,
                    "odd_space": 0, "crlf": False, "traditional": False}

    if "\r" in text:
        report["crlf"] = True
        text = text.replace("\r\n", "\n").replace("\r", "\n")

    report["invisible"] = len(_INVISIBLE_RE.findall(text))
    text = _INVISIBLE_RE.sub("", text)

    report["variation"] = len(_VARIATION_RE.findall(text))
    text = _VARIATION_RE.sub("", text)

    report["control"] = len(_CTRL_RE.findall(text))
    text = _CTRL_RE.sub("", text)

    report["odd_space"] = len(_ODD_SPACE_RE.findall(text))
    text = _ODD_SPACE_RE.sub(" ", text)

    # 全角字母数字 → 半角。Word 粘贴常见，且会打断英文规则的 \b 边界。
    text = unicodedata.normalize("NFKC", text) if report["invisible"] else text

    report["traditional"] = looks_traditional(text)
    report["changed"] = any((report["invisible"], report["variation"],
                             report["control"], report["odd_space"], report["crlf"]))
    return text, report


def describe(report: Dict) -> list:
    """把报告转成给用户看的提示列表。"""
    out = []
    n = report.get("invisible", 0)
    if n:
        out.append({
            "level": "warn",
            "text": f"清除了 {n} 个零宽/不可见字符。这类字符会让所有检测规则失效，"
                    f"而知网、Turnitin 会把它们判定为篡改——如果你的文本"
                    f"经过别的「降 AI 率」工具处理过，那很可能就是它加的。",
        })
    if report.get("control"):
        out.append({"level": "warn",
                    "text": f"清除了 {report['control']} 个控制字符。"})
    if report.get("variation") or report.get("odd_space"):
        k = report.get("variation", 0) + report.get("odd_space", 0)
        out.append({"level": "info", "text": f"规范化了 {k} 处异常空白或变体字符。"})
    if report.get("traditional"):
        out.append({
            "level": "warn",
            "text": "检测到繁体中文。本引擎的词表与规则目前只覆盖简体，"
                    "繁体文本的检出率会明显偏低——报告显示「问题很少」"
                    "不代表文本真的干净。建议转成简体后再诊断。",
        })
    return out
