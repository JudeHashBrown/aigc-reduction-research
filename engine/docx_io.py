"""docx 读写。只用标准库：zipfile + ElementTree，不引入 python-docx。

.docx 是一个 zip，正文在 word/document.xml。段落是 <w:p>，
文字在其下的 <w:t> 里，可能被切成多个 run（Word 会因为拼写检查、
格式变化把一句话切成若干段）。所以取文本必须把同一段里的 run 拼起来。

写回采用**段落下标替换**：只改文字命中的那些段落，其余 XML 字节原样保留，
这样字体、样式、图片、公式、页眉页脚、批注全都不动。
整篇重新生成 docx 会丢掉这些东西，对毕业论文来说不可接受。
"""

import difflib
import io
import re
import zipfile
from typing import Dict, List, Tuple
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
DOC = "word/document.xml"

MAX_ZIP_BYTES = 40 * 1024 * 1024        # 压缩包上限
MAX_UNZIP_BYTES = 200 * 1024 * 1024     # 解压后上限，挡 zip 炸弹


class DocxError(Exception):
    pass


_NS_DECL = re.compile(rb'xmlns:([A-Za-z0-9_.-]+)\s*=\s*"([^"]+)"')


def _register_namespaces(raw: bytes) -> None:
    """把文档里声明过的命名空间前缀原样注册给 ElementTree。

    不注册的话，ET 序列化时会把 w: 重写成 ns0:。语义上等价，但
    真实论文的根节点常带 mc:Ignorable="w14 wp14" 这类**按前缀名**
    引用其他命名空间的属性——前缀一改，Word 可能直接判定文档损坏。
    只扫根标签那一段，正文里不会有 xmlns 声明。
    """
    # 不能用第一个 ">" 截断：document.xml 开头是 <?xml … ?>，
    # 第一个 ">" 属于 XML 声明，根标签的 xmlns 一个都扫不到。
    # 直接扫开头 8KB——xmlns 声明只可能出现在起始标签里，多扫无害。
    for prefix, uri in _NS_DECL.findall(raw[:8192]):
        try:
            ET.register_namespace(prefix.decode(), uri.decode())
        except (ValueError, UnicodeDecodeError):
            continue


def _check(data: bytes) -> zipfile.ZipFile:
    if len(data) > MAX_ZIP_BYTES:
        raise DocxError(f"文件过大（{len(data)//1024//1024} MB），上限 40 MB")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise DocxError("不是有效的 .docx 文件（可能是 .doc 旧格式，请先另存为 .docx）")
    if DOC not in zf.namelist():
        raise DocxError("这个 zip 里没有 word/document.xml，不是 Word 文档")
    total = sum(i.file_size for i in zf.infolist())
    if total > MAX_UNZIP_BYTES:
        raise DocxError("解压后体积异常，已拒绝")
    return zf


def _para_text(p: ET.Element) -> str:
    """把一个 <w:p> 下所有 run 的文字拼起来。

    要处理三种节点：w:t 正文、w:tab 制表符、w:br/w:cr 换行。
    删除修订（w:del）里的文字是已删内容，不能算进来。
    """
    parts: List[str] = []
    for node in p.iter():
        tag = node.tag
        if tag == W + "t":
            parts.append(node.text or "")
        elif tag == W + "tab":
            parts.append("\t")
        elif tag in (W + "br", W + "cr"):
            parts.append("\n")
    return "".join(parts)


def extract(data: bytes) -> Tuple[str, Dict]:
    """取出正文。返回 (文本, 元信息)。

    元信息里的 para_map 记录「文本里第几段 ← docx 里第几个 w:p」，
    写回时按它定位，避免空段落、表格、图片段落错位。
    """
    zf = _check(data)
    raw = zf.read(DOC)
    _register_namespaces(raw)
    root = ET.fromstring(raw)
    body = root.find(W + "body")
    if body is None:
        raise DocxError("文档结构异常：找不到 body")

    paras, para_map = [], []
    for idx, p in enumerate(body.iter(W + "p")):
        t = _para_text(p).strip()
        if not t:
            continue
        para_map.append(idx)
        paras.append(t)

    if not paras:
        raise DocxError("文档里没有可提取的正文（可能内容都在文本框或图片里）")

    text = "\n\n".join(paras)
    return text, {
        "n_paragraphs": len(paras),
        "n_chars": len(text),
        "para_map": para_map,
        "has_tables": body.find(f".//{W}tbl") is not None,
        "has_tracked_changes": (body.find(f".//{W}ins") is not None
                                or body.find(f".//{W}del") is not None),
    }


def _restore_root_namespaces(original: bytes, serialized: bytes) -> bytes:
    """Restore unused xmlns declarations referenced by mc:Ignorable.

    ElementTree drops namespace declarations that are not attached to an
    element.  Word still requires declarations such as w14/wp14 when their
    prefixes appear only inside the string value of ``mc:Ignorable``.
    """
    root_start = re.search(rb'<(?:[A-Za-z0-9_.-]+:)?document\b', serialized)
    if not root_start:
        return serialized
    root_end = serialized.find(b">", root_start.start())
    if root_end < 0:
        return serialized
    root_tag = serialized[root_start.start():root_end]
    additions = []
    for prefix, uri in _NS_DECL.findall(original[:8192]):
        marker = b"xmlns:" + prefix + b"="
        if marker not in root_tag:
            additions.append(b' xmlns:' + prefix + b'="' + uri + b'"')
    if not additions:
        return serialized
    return serialized[:root_end] + b"".join(additions) + serialized[root_end:]


def _set_para_text(p: ET.Element, new_text: str) -> None:
    """Patch text across existing runs without flattening local formatting.

    Equal text stays in its original run.  Replacements spanning multiple runs
    are distributed in proportion to the old run lengths, so mixed bold,
    italics, hyperlinks and field anchors remain local instead of making the
    entire paragraph inherit the first run's style.
    """
    ts = [n for n in p.iter() if n.tag == W + "t"]
    if not ts:
        return
    old_parts = [n.text or "" for n in ts]
    old_text = "".join(old_parts)
    if old_text == new_text:
        return
    if any(n.tag in (W + "tab", W + "br", W + "cr") for n in p.iter()):
        raise DocxError("段落含制表符或手动换行，修改后无法安全保持 run 格式；请复制文本后手工替换。")

    starts, pos = [], 0
    for part in old_parts:
        starts.append((pos, pos + len(part)))
        pos += len(part)
    buffers = [""] * len(ts)

    def append_equal(i1: int, i2: int, segment: str) -> None:
        cursor = 0
        for idx, (start, end) in enumerate(starts):
            left, right = max(i1, start), min(i2, end)
            if right > left:
                length = right - left
                buffers[idx] += segment[cursor:cursor + length]
                cursor += length

    def append_replacement(i1: int, i2: int, segment: str) -> None:
        if not segment:
            return
        covered = [(idx, max(0, min(i2, end) - max(i1, start)))
                   for idx, (start, end) in enumerate(starts)
                   if min(i2, end) > max(i1, start)]
        if not covered:  # pure insertion: inherit the nearest surrounding run
            idx = next((idx for idx, (_start, end) in enumerate(starts) if end >= i1),
                       len(ts) - 1)
            buffers[idx] += segment
            return
        total = sum(weight for _, weight in covered)
        consumed = 0
        cumulative = 0
        for n, (idx, weight) in enumerate(covered):
            cumulative += weight
            end = len(segment) if n == len(covered) - 1 else round(
                len(segment) * cumulative / total)
            buffers[idx] += segment[consumed:end]
            consumed = end

    matcher = difflib.SequenceMatcher(None, old_text, new_text)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            append_equal(i1, i2, new_text[j1:j2])
        elif tag in ("replace", "insert"):
            append_replacement(i1, i2, new_text[j1:j2])

    for node, value in zip(ts, buffers):
        node.text = value
        if value[:1].isspace() or value[-1:].isspace():
            node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def replace(data: bytes, new_paragraphs: List[str], meta: Dict) -> bytes:
    """按段落下标写回，其余 XML 与所有其他文件原样保留。"""
    if len(new_paragraphs) != len(meta["para_map"]):
        raise DocxError(f"段落数对不上：改写后 {len(new_paragraphs)} 段，"
                        f"原文 {len(meta['para_map'])} 段。写回中止，以免错位。")
    zf = _check(data)
    raw = zf.read(DOC)
    _register_namespaces(raw)
    root = ET.fromstring(raw)
    body = root.find(W + "body")
    all_p = list(body.iter(W + "p"))
    wanted = dict(zip(meta["para_map"], new_paragraphs))
    for idx, p in enumerate(all_p):
        if idx in wanted:
            _set_para_text(p, wanted[idx])

    new_doc = ET.tostring(root, encoding="UTF-8", xml_declaration=True)
    new_doc = _restore_root_namespaces(raw, new_doc)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zo:
        for item in zf.infolist():
            zo.writestr(item, new_doc if item.filename == DOC else zf.read(item.filename))
    return out.getvalue()
