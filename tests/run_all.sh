#!/usr/bin/env bash
# 全套测试。任何一项失败即退出非零。
set -e
cd "$(dirname "$0")/.."
for t in tests/test_invariants.py tests/test_guard_en.py tests/test_docx.py tests/test_pdf.py tests/test_submit.py tests/test_llm_layer.py tests/run_function_tests.py tests/test_humanizer_cn.py tests/test_humanizer_bilingual.py tests/test_billing.py tests/test_stripe_payments.py tests/test_workspace_store.py tests/test_auth_store.py tests/test_auth_server.py tests/test_trial_session.py tests/test_server.py tests/test_workspace_api.py tests/test_trial_server.py tests/test_trial_lan.py; do
  printf '%-30s' "$(basename "$t")"
  if out=$(python3 "$t" 2>/dev/null); then
    echo "${out##*$'\n'}"
  else
    echo "失败"; echo "$out"; exit 1
  fi
done
echo "—— 全部通过 ——"
