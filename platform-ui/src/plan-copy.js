// Server prices and entitlements are authoritative; only display copy is localized here.
const ENGLISH_PLANS = {
  free: { name: "Free experience", description: "Free Chinese and English rule analysis, with 800 characters for a first conservative rewrite." },
  pack_3k: { name: "Small pack", description: "For a chapter or short draft. It does not renew automatically." },
  pack_10k: { name: "Paper pack", description: "For a short paper or several rounds of focused revision." },
  pack_30k: { name: "Large paper pack", description: "For longer papers and asynchronous chunked processing." },
  student_month: { name: "Student 30-day pass", description: "One-time purchase: 20,000 characters, valid for 30 days. No automatic renewal." },
  pro_month: { name: "Frequent-use 30-day pass", description: "One-time purchase: 60,000 characters, valid for 30 days. No automatic renewal." },
};

export function localizedPlanName(plan, isEnglish) {
  return isEnglish ? (ENGLISH_PLANS[plan.id]?.name || plan.name || plan.id) : (plan.name || plan.id);
}

export function localizedPlanDescription(plan, isEnglish) {
  if (!isEnglish) return plan.description || "服务端当前配置的额度产品。";
  return ENGLISH_PLANS[plan.id]?.description || plan.description || "An entitlement currently configured by the service.";
}
