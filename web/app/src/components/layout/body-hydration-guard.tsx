import Script from "next/script";

/**
 * Browser extensions (e.g. injecting `vc-init` on <body>) can alter the DOM
 * before React hydrates. This runs before Next.js hydration to drop known
 * extension classes so server HTML and the client tree stay aligned.
 */
const guardScript = `
(function () {
  var extensionClasses = ["vc-init"];
  function stripExtensionBodyClasses() {
    var body = document.body;
    if (!body) return;
    for (var i = 0; i < extensionClasses.length; i++) {
      body.classList.remove(extensionClasses[i]);
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", stripExtensionBodyClasses, {
      once: true,
    });
  } else {
    stripExtensionBodyClasses();
  }
})();
`;

export function BodyHydrationGuard() {
  return (
    <Script id="mycelium-body-hydration-guard" strategy="beforeInteractive">
      {guardScript}
    </Script>
  );
}
