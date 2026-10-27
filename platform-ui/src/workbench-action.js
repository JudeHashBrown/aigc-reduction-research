export function workbenchAction(report) {
  if (!report) return "analyze";
  // A diagnosis describes the draft; it never blocks a requested modification.
  // The rewrite service decides which safe changes to accept for the full text.
  return "rewrite";
}

export function canStartModification({ report, llmConfigured, allowedStrengths, mode, withinJobLimit, hasEnoughBalance }) {
  return workbenchAction(report) === "rewrite" && Boolean(llmConfigured)
    && allowedStrengths.includes(mode) && withinJobLimit && hasEnoughBalance;
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
