"""PDF 提取测试。

重点测行合并：PDF 每个视觉行都是硬换行，合并错了会让分句分段系统性失效，
而界面照样显示「问题很少」——这种错误不会报错，只会悄悄降低检出率。
PDF 本体解析交给 pypdf，这里只用一个手工构造的最小 PDF 验证管道通不通。
"""
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine"))

import pdf_io  # noqa: E402


def minimal_pdf(lines):
    """手工拼一个最小合法 PDF（Helvetica，仅 ASCII），不依赖任何外部工具。"""
    body = "BT /F1 12 Tf 72 720 Td 14 TL\n"
    for ln in lines:
        body += f"({ln}) Tj T*\n"
    body += "ET"
    stream = zlib.compress(body.encode("latin-1"))
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream)
        + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objs) + 1, xref))
    return bytes(out)


def t_merge_wrapped_lines():
    """折行必须拼回去，否则「研究表\\n明」永远匹配不到「研究表明」。"""
    got = pdf_io._merge_lines(
        "研究表明该方法在多个数据集上都\n"
        "取得了良好的效果，具有重要的理论\n"
        "意义。\n"
        "下一段从这里开始，继续论述相关的\n"
        "技术细节与实现方案。")
    assert got.split("\n\n")[0] == "研究表明该方法在多个数据集上都取得了良好的效果，具有重要的理论意义。", got


def t_drop_page_numbers():
    got = pdf_io._merge_lines("第一段内容在这里，长度足够构成一整行文字。\n12\n"
                              "第二段内容在这里，长度也足够构成一整行文字。")
    assert "12" not in got, got


def t_split_on_headings():
    got = pdf_io._merge_lines(
        "上一段的最后一句话写在这里，长度足够。\n"
        "一、研究背景\n"
        "本章介绍研究背景，内容长度也足够构成一行。")
    assert "一、研究背景" in got.split("\n\n"), got.split("\n\n")


def t_english_gets_space_chinese_does_not():
    en = pdf_io._merge_lines("This method works well across many\n"
                             "different experimental conditions here")
    assert "many different" in en, en
    zh = pdf_io._merge_lines("这个方法在很多不同的实验条件下都能\n"
                             "取得比较稳定的效果与表现")
    assert "都能取得" in zh, zh


def t_extract_real_pdf():
    data = minimal_pdf(["Research shows that this method is",
                        "effective and has important value.",
                        "",
                        "The framework serves as a pivotal tool."])
    text, meta = pdf_io.extract(data)
    assert "Research shows" in text, text
    assert meta["n_pages"] == 1, meta


def t_rejects_non_pdf():
    for bad in (b"hello world", b"PK\x03\x04not a pdf"):
        try:
            pdf_io.extract(bad)
        except pdf_io.PdfError:
            pass
        else:
            raise AssertionError("非 PDF 必须报 PdfError")


def t_scanned_pdf_gives_clear_error():
    """取不到文字时必须明确说原因，不能返回空字符串让用户以为文档干净。"""
    try:
        pdf_io.extract(minimal_pdf([]))
    except pdf_io.PdfError as e:
        assert "扫描" in str(e) or "取不到文字" in str(e), str(e)
    else:
        raise AssertionError("空 PDF 应当报错而不是静默返回空文本")


def t_notices_say_pdf_is_read_only():
    _, meta = pdf_io.extract(minimal_pdf(
        ["Some text here for testing purposes, long enough to pass",
         "the minimum length check that guards against scanned PDFs."]))
    texts = " ".join(n["text"] for n in pdf_io.notices(meta))
    assert "不提供导出" in texts, texts


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("t_")]
    for fn in tests:
        fn()
    print(f"✓ PDF 提取 {len(tests)} 项全部通过")
