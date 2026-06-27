import http from "node:http";
import httpProxy from "http-proxy";

const GATEWAY_PORT = Number(process.env.DEV_GATEWAY_PORT ?? 9911);
const LANDING_TARGET = process.env.LANDING_TARGET ?? "http://127.0.0.1:4321";
const APP_TARGET = process.env.APP_TARGET ?? "http://127.0.0.1:3001";
const API_TARGET = process.env.API_TARGET ?? "http://127.0.0.1:8000";

const proxy = httpProxy.createProxyServer({
  ws: true,
  changeOrigin: true,
  xfwd: true,
});

proxy.on("error", (error, _req, res) => {
  console.error("[dev-gateway] proxy error:", error.message);
  if (res && !res.headersSent && typeof res.writeHead === "function") {
    res.writeHead(502, { "Content-Type": "text/plain" });
    res.end("Bad gateway");
  }
});

/** Mirrors web/infra/nginx/default.conf path precedence. */
function resolveTarget(pathname) {
  if (pathname.startsWith("/api/")) {
    return API_TARGET;
  }
  if (pathname.startsWith("/admin/")) {
    return API_TARGET;
  }
  if (pathname === "/login" || pathname.startsWith("/login/")) {
    return APP_TARGET;
  }
  if (pathname === "/signup" || pathname.startsWith("/signup/")) {
    return APP_TARGET;
  }
  if (pathname === "/app" || pathname.startsWith("/app/")) {
    return APP_TARGET;
  }
  if (pathname.startsWith("/_next/")) {
    return APP_TARGET;
  }
  if (pathname.startsWith("/_astro/")) {
    return LANDING_TARGET;
  }
  return LANDING_TARGET;
}

function proxyRequest(req, res) {
  const target = resolveTarget(req.url ?? "/");
  proxy.web(req, res, { target });
}

function proxyUpgrade(req, socket, head) {
  const pathname = req.url?.split("?")[0] ?? "/";
  const target = resolveTarget(pathname);
  proxy.ws(req, socket, head, { target });
}

const server = http.createServer(proxyRequest);
server.on("upgrade", proxyUpgrade);

server.listen(GATEWAY_PORT, "0.0.0.0", () => {
  console.log(`[dev-gateway] http://localhost:${GATEWAY_PORT}`);
  console.log(`[dev-gateway] landing → ${LANDING_TARGET}`);
  console.log(`[dev-gateway] app     → ${APP_TARGET}`);
  console.log(`[dev-gateway] api     → ${API_TARGET}`);
});
