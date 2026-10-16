"""docx 读写测试。自己造一个最小合法 docx，不依赖外部样例文件。"""
import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine"))

import docx_io  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

_CT = '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="xml" ContentType="application/xml"/>
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>'''

_RELS = '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''


def make_docx(paragraphs, split_runs=False):
    """split_runs=True 时把每段切成多个 run，模拟 Word 的真实产物。"""
    body = []
    for text in paragraphs:
        if not text:
            body.append('<w:p/>')
            continue
        if split_runs and len(text) > 3:
            mid = len(text) // 2
            runs = (f'<w:r><w:rPr><w:b/></w:rPr><w:t>{text[:mid]}</w:t></w:r>'
                    f'<w:r><w:t>{text[mid:]}</w:t></w:r>')
        else:
            runs = f'<w:r><w:t>{text}</w:t></w:r>'
        body.append(f'<w:p>{runs}</w:p>')
    doc = (f'<?xml version="1.0" encoding="UTF-8"?>'
           f'<w:document xmlns:w="{W}"><w:body>{"".join(body)}'
           f'<w:sectPr/></w:body></w:document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("word/document.xml", doc)
        z.writestr("word/keepme.bin", b"\x01\x02\x03")   # 无关文件，写回后必须还在
    return buf.getvalue()


def make_docx_xml(document_xml):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("word/document.xml", document_xml)
    return buf.getvalue()


def t_extract_joins_runs():
    """Word 会把一句话切成多个 run，取文本必须拼回来。"""
    data = make_docx(["研究表明该方法有效。", "", "第二段内容在这里。"], split_runs=True)
    text, meta = docx_io.extract(data)
    assert text == "研究表明该方法有效。\n\n第二段内容在这里。", repr(text)
    assert meta["n_paragraphs"] == 2, meta
    # 空段落不能占位，否则写回时下标会错开
    assert meta["para_map"] == [0, 2], meta["para_map"]


def t_roundtrip_preserves_other_files():
    data = make_docx(["原文第一段。", "原文第二段。"])
    text, meta = docx_io.extract(data)
    out = docx_io.replace(data, ["改后第一段。", "改后第二段。"], meta)
    text2, _ = docx_io.extract(out)
    assert text2 == "改后第一段。\n\n改后第二段。", repr(text2)
    with zipfile.ZipFile(io.BytesIO(out)) as z:
        assert z.read("word/keepme.bin") == b"\x01\x02\x03", "无关文件被改坏了"
        assert "[Content_Types].xml" in z.namelist()


def t_roundtrip_keeps_formatting_run():
    """改写后第一个 run 必须还在（字体格式挂在它上面）。"""
    data = make_docx(["需要保留加粗格式的一段话。"], split_runs=True)
    text, meta = docx_io.extract(data)
    out = docx_io.replace(data, ["换成完全不同的内容。"], meta)
    with zipfile.ZipFile(io.BytesIO(out)) as z:
        xml = z.read("word/document.xml").decode()
    assert "<w:b" in xml, "加粗格式丢了"          # ET 输出成 <w:b />，带空格
    rewritten, _ = docx_io.extract(out)
    assert rewritten == "换成完全不同的内容。"
    # 命名空间前缀必须原样保留。ET 默认会把 w: 重写成 ns0:，语义等价但
    # 真实论文根节点带 mc:Ignorable="w14 wp14" 这类按前缀名引用的属性，
    # 前缀一改 Word 可能直接判定文档损坏。
    assert "<w:document" in xml and "ns0:" not in xml, "命名空间前缀被 ET 改写了"
    root = docx_io.ET.fromstring(xml)
    run_texts = [n.text or "" for n in root.iter(docx_io.W + "t")]
    assert all(run_texts), f"改写把局部格式 run 清空了: {run_texts}"


def t_unchanged_roundtrip_does_not_flatten_runs():
    text = "前半部分加粗，后半部分正常。"
    data = make_docx([text], split_runs=True)
    _, meta = docx_io.extract(data)
    out = docx_io.replace(data, [text], meta)
    with zipfile.ZipFile(io.BytesIO(out)) as z:
        root = docx_io.ET.fromstring(z.read("word/document.xml"))
    parts = [n.text or "" for n in root.iter(docx_io.W + "t")]
    assert len(parts) == 2 and "" not in parts
    assert "".join(parts) == text


def t_tracked_changes_keep_inserted_current_text():
    doc = (f'<?xml version="1.0" encoding="UTF-8"?>'
           f'<w:document xmlns:w="{W}"><w:body><w:p>'
           f'<w:del><w:r><w:delText>旧结论无效。</w:delText></w:r></w:del>'
           f'<w:ins><w:r><w:t>新结论有效。</w:t></w:r></w:ins>'
           f'</w:p><w:p><w:r><w:t>第二段。</w:t></w:r></w:p>'
           f'<w:sectPr/></w:body></w:document>')
    text, meta = docx_io.extract(make_docx_xml(doc))
    assert text == "新结论有效。\n\n第二段。"
    assert meta["has_tracked_changes"] is True
    assert meta["n_paragraphs"] == 2


def t_unused_ignorable_namespaces_survive_export():
    mc = "http://schemas.openxmlformats.org/markup-compatibility/2006"
    w14 = "http://schemas.microsoft.com/office/word/2010/wordml"
    wp14 = "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing"
    doc = (f'<?xml version="1.0" encoding="UTF-8"?>'
           f'<w:document xmlns:w="{W}" xmlns:mc="{mc}" xmlns:w14="{w14}" '
           f'xmlns:wp14="{wp14}" mc:Ignorable="w14 wp14"><w:body>'
           f'<w:p><w:r><w:t>正文内容。</w:t></w:r></w:p><w:sectPr/>'
           f'</w:body></w:document>')
    data = make_docx_xml(doc)
    text, meta = docx_io.extract(data)
    out = docx_io.replace(data, [text], meta)
    with zipfile.ZipFile(io.BytesIO(out)) as z:
        xml = z.read("word/document.xml")
    assert b'mc:Ignorable="w14 wp14"' in xml
    assert b'xmlns:w14=' in xml and b'xmlns:wp14=' in xml


def t_table_cells_and_body_paragraphs_keep_their_structure():
    doc = (f'<?xml version="1.0" encoding="UTF-8"?>'
           f'<w:document xmlns:w="{W}"><w:body>'
           f'<w:p><w:r><w:t>正文前。</w:t></w:r></w:p>'
           f'<w:tbl><w:tr><w:tc><w:p><w:r><w:t>表格单元格。</w:t></w:r></w:p>'
           f'</w:tc></w:tr></w:tbl>'
           f'<w:p><w:r><w:t>正文后。</w:t></w:r></w:p>'
           f'<w:sectPr/></w:body></w:document>')
    data = make_docx_xml(doc)
    _, meta = docx_io.extract(data)
    assert meta["has_tables"] is True
    out = docx_io.replace(data, ["改后正文前。", "改后单元格。", "改后正文后。"], meta)
    extracted, _ = docx_io.extract(out)
    assert extracted == "改后正文前。\n\n改后单元格。\n\n改后正文后。"
    with zipfile.ZipFile(io.BytesIO(out)) as z:
        root = docx_io.ET.fromstring(z.read("word/document.xml"))
    assert len(list(root.iter(docx_io.W + "tbl"))) == 1
    assert len(list(root.iter(docx_io.W + "tc"))) == 1


def t_hyperlink_container_and_bold_run_survive_rewrite():
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    doc = (f'<?xml version="1.0" encoding="UTF-8"?>'
           f'<w:document xmlns:w="{W}" xmlns:r="{rel}"><w:body><w:p>'
           f'<w:r><w:rPr><w:b/></w:rPr><w:t>参见</w:t></w:r>'
           f'<w:hyperlink r:id="rId9"><w:r><w:t>研究来源</w:t></w:r></w:hyperlink>'
           f'</w:p><w:sectPr/></w:body></w:document>')
    data = make_docx_xml(doc)
    _, meta = docx_io.extract(data)
    out = docx_io.replace(data, ["请参见研究来源"], meta)
    with zipfile.ZipFile(io.BytesIO(out)) as z:
        root = docx_io.ET.fromstring(z.read("word/document.xml"))
    links = list(root.iter(docx_io.W + "hyperlink"))
    assert len(links) == 1 and links[0].get("{" + rel + "}id") == "rId9"
    assert list(root.iter(docx_io.W + "b"))


def t_paragraph_count_mismatch_refused():
    data = make_docx(["一段。", "两段。"])
    _, meta = docx_io.extract(data)
    try:
        docx_io.replace(data, ["只给一段。"], meta)
    except docx_io.DocxError as e:
        assert "段落数对不上" in str(e)
    else:
        raise AssertionError("段落数不匹配时必须拒绝写回，否则会整篇错位")


def t_rejects_garbage():
    for bad, why in ((b"not a zip at all", "非 zip"),
                     (zipfile.ZipFile(io.BytesIO(), "w").close() or b"", "空")):
        try:
            docx_io.extract(bad or b"PK\x05\x06" + b"\x00" * 18)
        except docx_io.DocxError:
            pass
        else:
            raise AssertionError(f"{why} 应当报 DocxError")


def t_empty_doc_refused():
    try:
        docx_io.extract(make_docx(["", ""]))
    except docx_io.DocxError as e:
        assert "没有可提取的正文" in str(e)
    else:
        raise AssertionError("全空文档应当报错，而不是返回空字符串")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("t_")]
    for fn in tests:
        fn()
    print(f"✓ docx 读写 {len(tests)} 项全部通过")
