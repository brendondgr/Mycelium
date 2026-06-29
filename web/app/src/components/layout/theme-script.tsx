/**
 * Applies the persisted light/dark choice to <html> before first paint so the
 * dashboard never flashes the wrong theme. Theme is keyed off
 * `[data-theme="dark"]` in the shared token sheet; absence means light.
 *
 * Must live in the root layout so next/script's beforeInteractive strategy
 * injects it into <head> ahead of hydration. The matching client hook lives in
 * `lib/portal/theme.ts`.
 */
import Script from "next/script";

const THEME_KEY = "mycelium-theme";

const themeScript = `
(function () {
  try {
    var t = localStorage.getItem(${JSON.stringify(THEME_KEY)});
    if (t === "dark" || t === "light") {
      document.documentElement.setAttribute("data-theme", t);
    }
  } catch (e) {}
})();
`;

export function ThemeScript() {
  return (
    <Script
      id="mycelium-theme-script"
      strategy="beforeInteractive"
      dangerouslySetInnerHTML={{ __html: themeScript }}
    />
  );
}
