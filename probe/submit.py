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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--detector", help="检测器名称，例如 朱雀 / 知网 / 维普")
    ap.add_argument("--priority", default="P1", choices=["P1", "P2", "P3", "all"])
    ap.add_argument("--redo", action="store_true", help="连已填过的也重新做")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    rows, fields = load()
    if args.status:
        status(rows)
        return 0
    if not args.detector:
        sys.exit("请用 --detector 指定检测器名，例如：--detector 朱雀")

    todo = [r for r in rows
            if (args.priority == "all" or r.get("priority") == args.priority)
            and (args.redo or not (r.get("score") or "").strip())]
    if not todo:
        print("这一层已经填完了。")
        status(rows)
        return 0

    tier = args.priority
    print(f"\n检测器：{args.detector}    本轮 {len(todo)} 条"
          + (f"\n{tier}：{TIER[tier]}" if tier in TIER else ""))
    print("每条会自动复制到剪贴板。填分数回车即可；"
          "直接回车=跳过，输入 q=退出（已填的都已保存）\n")

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
