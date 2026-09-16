"""生成探针基准语料：AI 写的学术段落，与开发集严格分离。

为什么基准必须是 AI 文本：探针要测的是「消除某个特征能让检测器分数降多少」。
基准得先被判成高 AI，才有下降空间。真人论文放进去，检测器给 5%、
消融完还是 5%，任何规则的效应量都是 0——测不出东西，不是规则没用。

为什么必须重新生成：原来的 probe/bases/b01 与 samples/ai_sample.txt 是同一个文件
（MD5 都是 81cd0686…）。引擎是照着那篇调出来的，再拿它测效应量等于自测自考，
校准结果一定虚高，而且虚高多少无法估计。

生成条件照抄 lieflat 的对照实验设计：**不给任何写作风格指令，只给题目**。
加了风格要求就测不出模型的默认倾向，测到的是我们自己的提示词。

用法：
    export LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=...
    python3 probe/gen_bases.py [--out probe/bases] [--n 8]
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "engine"))

from llm import Client, LLMError          # noqa: E402

# 覆盖不同学科，避免单一领域的用词习惯被当成 AI 共性。
# 题目本身刻意写得普通——真实用户交上来的就是这种题。
TOPICS = [
    ("b11_材料", "石墨烯复合材料在锂电池负极中的应用"),
    ("b12_经济", "数字普惠金融对农村居民消费的影响"),
    ("b13_环境", "城市绿地布局对热岛效应的缓解作用"),
    ("b14_心理", "短视频使用时长与青少年注意力的关系"),
    ("b15_土木", "装配式建筑在高层住宅中的施工质量控制"),
    ("b16_农学", "水肥一体化技术对设施番茄产量的影响"),
    ("b17_法学", "个人信息保护法中知情同意规则的适用困境"),
    ("b18_医学", "二甲双胍在多囊卵巢综合征治疗中的作用机制"),
]

# 只说体裁和长度，不说风格。任何「要自然」「要像人写」的措辞都会污染基准。
SYS = "你是论文写作助手。"
USER = ("写一段{topic}的论文正文，400 到 600 字。"
        "只输出正文，不要标题、不要小标题、不要列表、不要 Markdown 标记。")


def clean(raw: str) -> str:
    """去掉模型可能带出来的标题行和 Markdown 残留。

    这里只清格式，不清任何 AI 特征——清了基准就没有下降空间了。
    """
    text = re.sub(r'^```[a-zA-Z]*\n?|```$', '', raw.strip(), flags=re.M)
    lines = [ln for ln in text.split("\n") if not ln.strip().startswith("#")]
    text = "\n".join(lines)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "bases"))
    ap.add_argument("--n", type=int, default=len(TOPICS))
    args = ap.parse_args()

    try:
        client = Client()
    except Exception as exc:                       # noqa: BLE001
        print(f"LLM 未配置：{exc}")
        return 1
    if not client.api_key or not client.base_url:
        print("LLM 未配置。请设置 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL。")
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"模型 {client.model}，生成 {args.n} 篇 -> {out_dir}")

    ok = 0
    for name, topic in TOPICS[:args.n]:
        try:
            raw = client.complete(SYS, USER.format(topic=topic), n=1)[0]
        except LLMError as exc:
            print(f"  {name:14s} 失败：{exc}")
            continue
        text = clean(raw)
        if len(text) < 200:
            print(f"  {name:14s} 跳过：只有 {len(text)} 字")
            continue
        (out_dir / f"{name}.txt").write_text(text + "\n", encoding="utf-8")
        print(f"  {name:14s} {len(text):4d} 字  {topic}")
        ok += 1
    print(f"完成 {ok}/{args.n}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
