/** Pass a located diagnosis finding to the server for guarded modification. */
export function reviewTargetFromFinding(finding) {
  if (!finding || typeof finding.pattern_id !== "string" || !finding.pattern_id
    || typeof finding.matched !== "string" || !finding.matched) return null;
  const { start, end } = finding;
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end <= start
    || end - start > 3500) return null;
  return {
    pattern_id: finding.pattern_id,
    start,
    end,
    matched: finding.matched,
  };
}
