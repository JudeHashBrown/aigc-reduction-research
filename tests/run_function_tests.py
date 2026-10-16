"""执行旧测试文件中未被 __main__ 覆盖到的 test_* 函数。

项目不依赖 pytest；这个小运行器避免“文件执行成功，但一半测试
根本没跑”的假绿灯。
"""
import importlib.util
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    path = ROOT / "tests" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def main():
    total = 0
    for name in ("test_invariants", "test_llm_layer"):
        module = load(name)
        funcs = [fn for key, fn in sorted(vars(module).items())
                 if key.startswith("test_") and inspect.isfunction(fn)]
        for fn in funcs:
            if inspect.signature(fn).parameters:
                raise RuntimeError(f"{name}.{fn.__name__} 需要 fixture，请单独提供运行器")
            fn()
            total += 1
    print(f"✓ 补充 test_* 函数 {total} 项全部通过")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "engine"))
    sys.path.insert(0, str(ROOT / "probe"))
    main()
