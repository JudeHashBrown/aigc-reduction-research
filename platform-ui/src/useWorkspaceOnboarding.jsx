import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  createOnboardingStore,
  onboardingOwner,
  onboardingPage,
  workspaceTourSteps,
} from "./workspace-onboarding.js";

const progress = createOnboardingStore(() => window.localStorage);

export function useWorkspaceOnboarding({ session, path, ready, hasManuscript, isEnglish, navigate }) {
  const owner = onboardingOwner(session);
  const page = onboardingPage(path, hasManuscript);
  const [active, setActive] = useState(null);
  const [replay, setReplay] = useState(null);
  const consumedReplay = useRef(null);
  const steps = useMemo(() => workspaceTourSteps(page, isEnglish), [page, isEnglish]);

  useEffect(() => {
    setActive(null);
    if (!ready || !owner || !page) return undefined;
    let cancelled = false;
    let timer;
    const manual = replay?.owner === owner && replay.page === page
      && replay !== consumedReplay.current;
    const openWhenReady = () => {
      if (cancelled || (!manual && !progress.shouldStart(owner, page))) return;
      const surface = document.querySelector(`[data-onboarding-page="${page}"]`);
      if (!surface || surface.getAttribute("data-tour-blocked") === "true"
          || document.querySelector(".rt-confirm-backdrop")) {
        timer = window.setTimeout(openWhenReady, 400);
        return;
      }
      if (manual) consumedReplay.current = replay;
      setActive({ owner, page });
    };
    timer = window.setTimeout(openWhenReady, manual ? 80 : 650);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [owner, page, ready, replay]);

  const start = useCallback(() => {
    if (!owner) return;
    const destination = page || "documents";
    setReplay({ owner, page: destination });
    if (!page) navigate("/app");
  }, [owner, page, navigate]);

  const finish = useCallback((reason) => {
    if (active?.owner === owner && active?.page === page) {
      progress.finish(owner, page, reason);
    }
    setActive(null);
  }, [active, owner, page]);

  const visible = ready && active?.owner === owner && active?.page === page;
  return { active: Boolean(visible), available: Boolean(owner), key: `${owner}:${page}`, steps, start, finish };
}
