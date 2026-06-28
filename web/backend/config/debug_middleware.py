import logging

logger = logging.getLogger("mycelium.csrf_debug")


class CsrfDebugMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in ("POST", "PATCH", "PUT", "DELETE"):
            csrf_cookie = request.COOKIES.get("csrftoken", "<missing>")
            csrf_header = request.META.get("HTTP_X_CSRFTOKEN", "<missing>")
            session = request.COOKIES.get("sessionid", "<missing>")
            origin = request.META.get("HTTP_ORIGIN", "<none>")
            referer = request.META.get("HTTP_REFERER", "<none>")
            host = request.META.get("HTTP_HOST", "<none>")
            logger.warning(
                "CSRF_DEBUG %s %s | cookie=%s | header=%s | match=%s | session=%s | origin=%s | host=%s | referer=%s",
                request.method,
                request.path,
                csrf_cookie[:8] if len(csrf_cookie) > 8 else csrf_cookie,
                csrf_header[:8] if len(csrf_header) > 8 else csrf_header,
                csrf_cookie == csrf_header,
                session[:8] if len(session) > 8 else session,
                origin,
                host,
                referer,
            )
        return self.get_response(request)
