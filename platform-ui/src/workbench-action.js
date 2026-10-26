export function workbenchAction(report) {
  if (!report) return "analyze";
  const findings = Array.isArray(report.findings) ? report.findings : [];
  const hasServerCandidateCount = Object.prototype.hasOwnProperty.call(report.summary || {}, "auto_rewrite_candidates");
  const canRewrite = hasServerCandidateCount
    ? Number(report.summary.auto_rewrite_candidates) > 0
    : findings.some((finding) => finding.handling === "rewrite"
        && finding.language !== "en"
        && !String(finding.pattern_id || "").startsWith("EN-"));
  if (canRewrite) return "rewrite";
  if (Number(report.summary?.findings || 0) > 0 || findings.length > 0) return "edit";
  return "none";
}

export function deterministicCleanupCount(report) {
  return Array.isArray(report?.findings) ? report.findings.filter((finding) =>
    finding.handling === "safe"
    && finding.language !== "en"
    && !String(finding.pattern_id || "").startsWith("EN-")).length : 0;
}

export function snapshotMatchesDraft(snapshot, revision, current, currentRevision) {
  return snapshot === current && revision === currentRevision;
}
