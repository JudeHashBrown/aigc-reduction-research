/** Only this review-only finding has a guarded, zero-credit adjustment path. */
export function reviewTargetFromFinding(finding) {
  if (finding?.pattern_id !== "EN-S01" || finding.handling !== "review") return null;
  const start = Number(finding.start);
  const end = Number(finding.end);
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end <= start
    || end - start > 500 || typeof finding.matched !== "string" || !finding.matched) return null;
  return {
    pattern_id: finding.pattern_id,
    start,
    end,
    matched: finding.matched,
  };
}
