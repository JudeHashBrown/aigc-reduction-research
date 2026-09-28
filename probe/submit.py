"""探针提交助手：逐个把变体复制到剪贴板，填回检测器分数。

手工改 CSV 太容易错行，而且中途退出就得从头找。这个脚本：
  - 按优先级过滤，只给你该做的那些
  - 自动把文本复制到剪贴板（macOS 用 pbcopy），直接去检测器粘贴
  - 每填一条立刻写回 manifest.csv，随时可以 Ctrl+C 退出再接着做

用法：
    python3 probe/submit.py --detector 朱雀              # 默认只做 P1
    python3 probe/submit.py --detector 知网 --priority P3
    python3 probe/submit.py --status                     # 只看进度
"""
import argparse
import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "out" / "manifest.csv"

TIER = {
    "P1": "基准 + 全清 —— 决定性实验。全清都推不动分数，"
          "就说明规则层对该检测器无效，后面的都可以省掉",
    "P2": "反向对照 —— lieflat 实测句长离散度人机无差异，预测它没有效应",
    "P3": "单特征消融 —— 只在 P1 出现可测降幅后才值得做",
}


def to_clipboard(text: str) -> bool:
    for cmd in (["pbcopy"], ["xclip", "-selection", "clipboard"], ["wl-copy"]):
        try:
            subprocess.run(cmd, input=text.encode(), check=True)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    return False


def load():
    if not MANIFEST.exists():
        sys.exit("还没有变体清单。先运行：python3 probe/build.py")
    with MANIFEST.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return rows, list(rows[0].keys())


def save(rows, fields):
    with MANIFEST.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def status(rows):
    print(f"\n{'层':4s} {'已填':>6s} {'总数':>6s}")
    for tier in ("P1", "P2", "P3"):
        sub = [r for r in rows if r.get("priority") == tier]
        done = sum(1 for r in sub if (r.get("score") or "").strip())
        if sub:
            print(f"{tier:4s} {done:6d} {len(sub):6d}   {TIER[tier][:40]}…")
    dets = {r["detector"] for r in rows if r.get("detector")}
    if dets:
        print(f"\n已用检测器：{', '.join(sorted(dets))}")



RANGE_DIR = ROOT / "out" / "_range"
RANGE_CSV = ROOT / "out" / "range.csv"
TACTICS_DIR = ROOT / "out" / "_tactics"
TACTICS_CSV = ROOT / "out" / "tactics.csv"

RANGE_CSV_ACTIVE = []

RANGE_NOTE = {
    "C0_原版重测": "b11 原版，9 月 20 日测过 100。再测一次，确认这 6 天里朱雀本身没变。"
                   "这一条如果不是 100，下面所有分数的可比性都没了。",
    "C1_朴素改写_Claude写": "对照 R4。**同样是不加约束的激进改写，同样的长度，只换了执笔的模型**"
                            "（R4 是 gpt，这条是 Claude）。H1 拿 0 分最可疑的解释就是"
                            "「朱雀认 gpt 不认 Claude」——这条专门用来验它。"
                            "这条如果也接近 0，H1 的 0 分就和那套 SKILL 没关系。",
    "C2_H1截到原版长度": "H1 的前几段，截到和原版一样长（794 → 545 字）。"
                          "H1 比原版长 47%，而朱雀对短文本的判定通常更保守。"
                          "这条隔离长度这个变量。",
    "C3_真人文本经gpt改写": "R1 那段真人文本（已实测 0 分）交给 gpt 改写一遍。"
                            "从 0 跳到 100，说明分数主要由「谁写的」决定；"
                            "仍然是低分，说明模型改写不会自动把文本打成 AI。",
    "R1_真人文本": "真人写的（低锚点）。如果这份也接近 100，说明朱雀在这类学术文本上"
                   "根本不区分人机，后面所有测量都没有意义。",
    "R2_b11两层改写后": "本产品当前的两层改写。白名单约束下只改了 3 个字。",
    "R3_另一篇AI原版": "另一篇 AI 原版。看是不是所有 AI 学术文本都顶到 100。",
    "R4_激进改写_行业做法": "不加任何约束直接让模型「降 AI 率」——竞品和 ChatGPT 的通行做法。"
                            "改了 59% 的字，丢了 6 个技术术语。它如果也压不下来，"
                            "说明这件事本身做不到，不是我们做得不够狠。",
    "T1_回译": "中→英→中。仍过模型，但翻译的条件分布受源文约束强得多，"
               "与自由生成不是一回事。全自动，产品上可行。",
    "T2_少样本条件化": "把真人写的文本当文风范例喂进去，让模型从「那位作者的分布」采样，"
                       "而不是从助手的默认分布。R4 失败很可能正是因为它始终在助手的默认分布里"
                       "——换措辞解决不了，换分布才可能。这条是四条里最可能成立的。",
    "H5_humanizer保守": "humanizer-zh-academic 的 SKILL，但跳过一切需要凭空添加内容的做法，"
                         "事实守卫保留。改了 31% 的字，我们的规则命中 5→1。",
    "H6_humanizer完整": "humanizer-zh-academic 的 SKILL，**完整执行**，包括「注入学者个性」"
                         "（承认局限 / 表达意外 / 留下判断）——那一节会加入原文没有的主观表述，"
                         "本质是编造，因此关掉了守卫。改了 76% 的字。"
                         "它 README 宣称「AIGC 检测率 >50% → 11%」，这一条就是验证那个说法。",
    "T3_非神经扰动": "纯代码：段内句子重排 + 长句拆分，完全不经模型采样，"
                     "因此不可能把 AI 统计特征重新采样回来。"
                     "它如果有效，说明检测器看句子顺序和句长结构；无效则说明它看的是别的东西。",
}


def _num(v):
    """分数必须是数字。之前 run_range 没有这道校验，把粘错的 shell 命令
    原样写进了 tactics.csv 的 score 列，两条数据报废。"""
    v = (v or "").strip().rstrip("%")
    if not v:
        return None
    try:
        f = float(v)
    except ValueError:
        return None
    return f if 0 <= f <= 100 else None


def _flush(csv_path, files, done):
    import csv as _csv
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=["item", "detector", "score", "n_chars"])
        w.writeheader()
        for f in files:                       # 按文件顺序写，行序稳定
            if f.stem in done:
                w.writerow(done[f.stem])


def run_range(detector, mode="range", reset=False, redo=False):
    import csv as _csv
    d, csv_path, title, why = (
        (TACTICS_DIR, TACTICS_CSV, "技术路线对比", """
  上一轮跑出了这个项目第一个不是 100 的数：H1 = 0，H2 = 32.25。
  在那之前原版、全清、两层改写、激进改写（改 59% 字数）全是 100。

  但这个 0 还不能信，有三个混淆没排除，C0-C3 四条对照就是为它们准备的：
    C0  朱雀自己这 6 天有没有变
    C1  是那套 SKILL 起作用，还是只因为 H1 是 Claude 写的、R4 是 gpt 写的
    C2  是不是只因为 H1 比原版长了 47%
    C3  真人文本过一遍模型，会不会自动变成 AI

  先看 C1。**C1 如果也接近 0，H1 的 0 分就与 humanizer 那套规则无关**，
  整件事变成「换个模型执笔」，那是完全不同的产品，也便宜得多。""")
        if mode == "tactics" else
        (RANGE_DIR, RANGE_CSV, "量程校验", """
  b11 的基准和全清都是 100 分。两边顶满时，测不出差异不代表规则没用，
  也可能是标尺没有分辨率。这几条先确认这把尺子分不分得出人写的和 AI 写的。"""))

    files = sorted(d.glob("*.txt"))
    if not files:
        sys.exit(f"{d} 里没有文件。先运行 python3 probe/tactics.py 生成。")

    # 已填过的分数必须活过这一轮。之前是每轮从空 out 重写 CSV，
    # 中途 Ctrl+C 就把上一轮填好的行一起抹掉了。
    done = {}
    if csv_path.exists():
        with csv_path.open(encoding="utf-8-sig") as f:
            for r in _csv.DictReader(f):
                if _num(r.get("score")) is not None:
                    done[r["item"]] = r
    if reset:
        print(f"  --reset：丢弃已填的 {len(done)} 条，全部重测")
        done = {}

    print("=" * 64)
    print(f"  {title}    检测器：{detector}    {len(files)} 条")
    print("=" * 64)
    print(why)
    todo = files if redo else [f for f in files if f.stem not in done]
    if not todo:
        print(f"\n  {len(files)} 条全部填过了。要重测：加 --reset\n")
    elif len(todo) < len(files):
        print(f"\n  已填 {len(done)} 条，本轮只做剩下的 {len(todo)} 条"
              f"（要连填过的一起重测：加 --redo）")
    print("\n  每条重复：⌘V 粘进朱雀 → 点检测 → 把百分比数字打回来 → 回车")
    print("  只接受 0-100 的数字。直接回车＝跳过这条，q＝退出（已填的都存好了）\n")

    for i, f in enumerate(todo, 1):
        name = f.stem
        text = f.read_text(encoding="utf-8")
        ok = to_clipboard(text)
        print(f"[{i}/{len(todo)}] {name}"
              + (f"    （上次 {done[name]['score']}）" if name in done else ""))
        note = RANGE_NOTE.get(name, "")
        if note:
            print(f"          {note}")
        print(f"          {len(text)} 字" + ("   ✓ 已复制到剪贴板" if ok else f"   ✗ 请手动打开 {f}"))

        quit_ = False
        while True:
            try:
                v = input("          朱雀给的分数（%）：").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n已退出，填过的都存好了。")
                quit_ = True
                break
            if v.lower() == "q":
                quit_ = True
                break
            if not v:
                print("          跳过这条")
                v = None
                break
            if _num(v) is None:
                print(f"          「{v}」不是 0-100 的数字。"
                      "是不是粘错窗口了？重新输一次（q 退出）")
                continue
            break
        if quit_:
            break
        if v is None:
            continue

        done[name] = {"item": name, "detector": detector,
                      "score": f"{_num(v):g}", "n_chars": len(text)}
        _flush(csv_path, files, done)

    print("\n" + "-" * 64)
    for f in files:
        r = done.get(f.stem)
        print(f"  {f.stem:26s} {(r['score'] + '%') if r else '（未测）':>8s}")
    print("-" * 64)
    print(f"  已存盘：{csv_path}")
    miss = [f.stem for f in files if f.stem not in done]
    if miss:
        print(f"  还差 {len(miss)} 条，重跑同一条命令会自动从这里接上")
    print("  把这张表发我。")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--detector", help="检测器名称，例如 朱雀 / 知网 / 维普")
    ap.add_argument("--priority", default="P1", choices=["P1", "P2", "P3", "all"])
    ap.add_argument("--redo", action="store_true", help="连已填过的也重新做")
    ap.add_argument("--limit", type=int,
                    help="本轮只做前 N 条。先跑通一对（--limit 2）再做全部，"
                         "比一口气做 16 条更容易发现流程里的问题")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--reset", action="store_true",
                    help="丢弃 tactics.csv / range.csv 里已填的分数，从头重测")
    ap.add_argument("--tactics", action="store_true",
                    help="技术路线对比：回译 / 少样本条件化 / 非神经扰动，"
                         "全是自动方案，看有没有哪条能推动分数")
    ap.add_argument("--range", action="store_true",
                    help="量程校验：先确认这把尺子分得出人写的和 AI 写的。"
                         "基准和全清都是 100 分时，效应量测不出来不是因为规则没用，"
                         "而是因为标尺顶满了，没有分辨率。")
    args = ap.parse_args()

    if args.range or args.tactics:
        if not args.detector:
            sys.exit("请用 --detector 指定检测器名")
        return run_range(args.detector, "tactics" if args.tactics else "range",
                         reset=args.reset, redo=args.redo)

    rows, fields = load()
    if args.status:
        status(rows)
        return 0
    if not args.detector:
        sys.exit("请用 --detector 指定检测器名，例如：--detector 朱雀")

    todo = [r for r in rows
            if (args.priority == "all" or r.get("priority") == args.priority)
            and (args.redo or not (r.get("score") or "").strip())]
    if args.limit:
        todo = todo[:args.limit]
    if not todo:
        print("这一层已经填完了。")
        status(rows)
        return 0

    tier = args.priority
    print("=" * 64)
    print(f"  检测器：{args.detector}      本轮 {len(todo)} 条")
    if tier in TIER:
        print(f"  {tier}：{TIER[tier]}")
    print("=" * 64)
    print("""
  怎么操作（每条重复一次）：
    1. 脚本已把这一条的文本复制到你的剪贴板
    2. 切到检测器网页，粘贴，点检测
    3. 把它给出的百分比数字填回下面，回车
    4. 自动跳到下一条

  朱雀（免费）：https://matrix.tencent.com/ai-detect/
    登录后每天 20 次文本检测，不登录只有 5 次——P1 要 16 次，记得先登录。
    只认 tencent.com 这个域名，其他域名的「朱雀付费版」都是蹭名字的。

  直接回车 = 跳过这条    输入 q = 退出（填过的都已存盘，下次接着做）
""")

    for i, r in enumerate(todo, 1):
        path = ROOT / "out" / r["base"] / (r["variant"] + ".txt")
        if not path.exists():
            print(f"[{i}/{len(todo)}] 缺文件 {path}，跳过")
            continue
        text = path.read_text(encoding="utf-8")
        ok = to_clipboard(text)
        tag = "基准（对照组）" if r["variant"] == "00_base" else (
              "全清（效果上界）" if r["variant"].startswith("ZZ_ALL") else
              f"单特征消融 {r['rule_id']}")
        print(f"[{i}/{len(todo)}] {r['base']} · {tag}")
        print(f"          {r['n_chars']} 字，引擎命中 {r['engine_findings']} 处"
              + ("   ✓ 已复制到剪贴板" if ok else "   ✗ 复制失败，请手动打开文件"))
        if not ok:
            print(f"          {path}")
        try:
            v = input("          该检测器给的分数（%）：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已退出，填过的都已保存。")
            break
        if v.lower() == "q":
            print("已退出，填过的都已保存。")
            break
        if not v:
            continue
        try:
            float(v.rstrip("%"))
        except ValueError:
            print("          不是数字，跳过这条")
            continue
        r["score"] = v.rstrip("%")
        r["detector"] = args.detector
        save(rows, fields)

    status(rows)
    print("\n填完后运行：python3 probe/analyze.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
