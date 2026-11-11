/**
 * Applies the persisted appearance to <html> before first paint so the
 * workspace never flashes the wrong look: the theme (`data-theme`, Night Forest
 * — dark — unless the reader chose light), the density (`data-density`) and the
 * motion level (`data-motion`) and whether the section rail is open
 * (`data-rail`). The matching client hooks live in
 * `lib/portal/theme.ts` and `lib/portal/appearance.ts`.
 *
 * Must live in the root layout so next/script's beforeInteractive strategy
 * injects it into <head> ahead of hydration. The matching client hook lives in
 * `lib/portal/theme.ts`.
 */
import Script from "next/script";

const THEME_KEY = "mycelium-theme";
const DENSITY_KEY = "mycelium-density";
const MOTION_KEY = "mycelium-motion";
const RAIL_KEY = "mycelium-rail-collapsed";

const themeScript = `
(function () {
  var html = document.documentElement;
  var t = "dark", d = "comfortable", m = "full", r = "expanded";
  try {
    var st = localStorage.getItem(${JSON.stringify(THEME_KEY)});
    if (st === "light" || st === "dark") t = st;
    var sd = localStorage.getItem(${JSON.stringify(DENSITY_KEY)});
    if (sd === "compact" || sd === "comfortable" || sd === "open") d = sd;
    var sm = localStorage.getItem(${JSON.stringify(MOTION_KEY)});
    if (sm === "full" || sm === "subtle" || sm === "none") m = sm;
    if (localStorage.getItem(${JSON.stringify(RAIL_KEY)}) === "1") r = "collapsed";
  } catch (e) {}
  html.setAttribute("data-theme", t);
  html.setAttribute("data-density", d);
  html.setAttribute("data-motion", m);
  html.setAttribute("data-rail", r);
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
