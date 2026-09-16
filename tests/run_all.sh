#!/usr/bin/env bash
# 全套测试。任何一项失败即退出非零。
set -e
cd "$(dirname "$0")/.."
for t in tests/test_invariants.py tests/test_docx.py tests/test_llm_layer.py tests/test_server.py; do
  printf '%-30s' "$(basename "$t")"
  if out=$(python3 "$t" 2>/dev/null); then
    echo "${out##*$'\n'}"
  else
    echo "失败"; echo "$out"; exit 1
  fi
done
echo "—— 全部通过 ——"
