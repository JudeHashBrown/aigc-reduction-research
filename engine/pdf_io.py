"""PDF 正文提取。

为什么 PDF 是只读的：PDF 存的是「把这个字形画在这个坐标」，没有段落概念，
也没有可靠的回写路径。改一个字要重排整页，字体、图表、公式、页码全会乱。
所以 PDF 只做诊断，不提供导出——那是诚实的能力边界，不是偷懒。

提取之后最关键的一步是**行合并**。PDF 每个视觉行都是一次硬换行，
不合并的话「研究表\n明该方法」会变成两段，我们的分句分段全部失效，
诊断结果会系统性偏低——而界面照样显示「问题很少」。
"""
import io
import re
from typing import Dict, List, Tuple

MAX_PDF_BYTES = 60 * 1024 * 1024
MAX_PAGES = 400


class PdfError(Exception):
    pass


# 行尾出现这些字符说明这一行确实结束了，不该和下一行合并
_LINE_END = "。！？；：…」』》】）】.!?;:\"')]"
# 行首出现这些说明下一行是新的结构单元
_NEW_BLOCK = re.compile(
    r'^\s*(?:'
    r'[一二三四五六七八九十百]+[、.]'          # 一、
    r'|第[一二三四五六七八九十百]+[章节条款]'    # 第三章
    r'|\d+(?:\.\d+)*[\s、.]'                  # 1.2.3
    r'|[（(]\s*\d+\s*[)）]'                    # (1)
    r'|[•·▪◦*-]\s'                             # 项目符号
    r'|摘\s*要|关键词|参考文献|致\s*谢|目\s*录|附\s*录|Abstract|Keywords|References'
    r')')
# 页眉页脚：孤立的页码行
_PAGE_NUM = re.compile(r'^\s*(?:[-—–]\s*)?\d{1,4}\s*(?:[-—–]\s*)?$')


def _merge_lines(raw: str) -> str:
    """把 PDF 的视觉行合并回段落。

    规则：上一行以句末标点收尾、或下一行是新结构单元、或上一行明显短于
    正常行宽（说明是段落最后一行），才断段；否则接上去。
    中文行之间不加空格，英文行之间加一个空格。
    """
    lines = [ln.rstrip() for ln in raw.split("\n")]
    lines = [ln for ln in lines if not _PAGE_NUM.match(ln)]
    # 估算正文行宽：取非空行长度的中位数，短于其 70% 的行视为段末
    lens = sorted(len(ln.strip()) for ln in lines if ln.strip())
    typical = lens[len(lens) // 2] if lens else 0
    short = typical * 0.7

    out: List[str] = []
    buf = ""
    for ln in lines:
        t = ln.strip()
        if not t:
            if buf:
                out.append(buf)
                buf = ""
            continue
        if not buf:
            buf = t
            continue
        prev = buf[-1]
        if prev in _LINE_END or _NEW_BLOCK.match(t) or len(buf) < short:
            out.append(buf)
            buf = t
        else:
            # 中文之间不加空格；英文单词跨行时补一个空格
            sep = "" if (_is_cjk(prev) or _is_cjk(t[0])) else " "
            buf = buf + sep + t
    if buf:
        out.append(buf)
    return "\n\n".join(out)


def _is_cjk(ch: str) -> bool:
    return "　" <= ch <= "鿿" or "＀" <= ch <= "￯"


def extract(data: bytes) -> Tuple[str, Dict]:
    """提取正文，返回 (文本, 元信息)。"""
    if len(data) > MAX_PDF_BYTES:
        raise PdfError(f"文件过大（{len(data)//1024//1024} MB），上限 60 MB")
    if not data.startswith(b"%PDF"):
        raise PdfError("不是有效的 PDF 文件")
    try:
        from pypdf import PdfReader
    except ImportError:
        raise PdfError("缺少 pypdf。请运行：python3 -m pip install pypdf")

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:                       # noqa: BLE001
        raise PdfError(f"解析失败：{exc}")

    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")                     # 很多论文只是设了空密码的打印限制
        except Exception:
            raise PdfError("PDF 有密码保护，请先解除保护后再上传")

    pages = reader.pages
    n_pages = len(pages)
    if n_pages > MAX_PAGES:
        raise PdfError(f"共 {n_pages} 页，超过 {MAX_PAGES} 页上限")

    chunks, empty = [], 0
    for pg in pages[:MAX_PAGES]:
        try:
            t = pg.extract_text() or ""
        except Exception:                          # noqa: BLE001
            t = ""
        if len(t.strip()) < 10:
            empty += 1
        chunks.append(t)

    raw = "\n".join(chunks)
    text = _merge_lines(raw)
    n_cjk = len(re.findall(r'[一-鿿]', text))

    if len(text.strip()) < 50:
        raise PdfError(
            "这个 PDF 里取不到文字。常见原因：整篇是扫描图片，"
            "或字体没有嵌入 ToUnicode 映射表。"
            "解决办法是用原始的 Word 文件，或者先做 OCR。")

    return text, {
        "n_pages": n_pages,
        "n_chars": len(text),
        "n_paragraphs": text.count("\n\n") + 1,
        "empty_pages": empty,
        "cjk_ratio": round(n_cjk / max(1, len(text)), 3),
    }


def notices(meta: Dict) -> List[Dict]:
    """提取质量提示。PDF 的提取质量参差，必须让用户知道可信度。"""
    out = [{
        "level": "info",
        "text": "PDF 只做诊断，不提供导出——PDF 存的是字形坐标而不是段落，"
                "改一个字要重排整页。定位到问题后，请回原始 Word 文件里修改。",
    }]
    if meta.get("empty_pages"):
        out.append({
            "level": "warn",
            "text": f"{meta['n_pages']} 页里有 {meta['empty_pages']} 页取不到文字，"
                    f"多半是扫描图或公式图。这些页的内容没有参与诊断，"
                    f"报告只覆盖能取到文字的部分。",
        })
    if meta.get("cjk_ratio", 1) < 0.2 and meta.get("n_chars", 0) > 500:
        out.append({
            "level": "warn",
            "text": "提取到的中文很少。如果原文是中文论文，"
                    "说明字体缺少 ToUnicode 映射，提取结果不可靠。",
        })
    out.append({
        "level": "info",
        "text": "PDF 的换行是按视觉行排的，本工具已按标点和行宽把它们合并回段落，"
                "但难免有误。如果看到句子被切断，以原始 Word 文件的诊断结果为准。",
    })
    return out
