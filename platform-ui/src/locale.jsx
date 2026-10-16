import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { GlobeHemisphereWest } from "@phosphor-icons/react";

const LocaleContext = createContext(null);
const STORAGE_KEY = "rightthesis-ui-locale";

function initialLocale() {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "en" ? "en" : "zh";
  } catch {
    return "zh";
  }
}

export function LocaleProvider({ children }) {
  const [locale, setLocale] = useState(initialLocale);

  useEffect(() => {
    document.documentElement.lang = locale === "en" ? "en" : "zh-CN";
    document.documentElement.dataset.locale = locale;
    document.title = locale === "en" ? "RightThesis · Faithful academic rewriting" : "RightThesis · 学术表达检测与保真改写";
    document.querySelector('meta[name="description"]')?.setAttribute(
      "content",
      locale === "en"
        ? "RightThesis explainable academic-expression review and faithful rewriting platform"
        : "RightThesis 可解释学术表达检查与保真改写平台",
    );
    try {
      window.localStorage.setItem(STORAGE_KEY, locale);
    } catch {
      // The language switch still works when storage is unavailable.
    }
  }, [locale]);

  const value = useMemo(() => ({
    locale,
    isEnglish: locale === "en",
    setLocale,
    toggleLocale: () => setLocale((current) => (current === "zh" ? "en" : "zh")),
  }), [locale]);

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale() {
  const context = useContext(LocaleContext);
  if (!context) throw new Error("useLocale must be used inside LocaleProvider");
  return context;
}

export function LanguageToggle({ className = "" }) {
  const { locale, toggleLocale } = useLocale();
  const english = locale === "en";
  const label = english ? "切换到中文界面" : "Switch interface to English";

  return (
    <button
      type="button"
      className={`rt-language-toggle ${className}`.trim()}
      onClick={toggleLocale}
      aria-label={label}
      title={label}
    >
      <GlobeHemisphereWest size={17} weight="bold" aria-hidden="true" />
      <span className={english ? "" : "is-active"}>中</span>
      <i aria-hidden="true">/</i>
      <span className={english ? "is-active" : ""}>EN</span>
    </button>
  );
}
