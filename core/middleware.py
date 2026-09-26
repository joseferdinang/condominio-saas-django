from django.http import HttpResponse


class RequestSizeLimitMiddleware:
    """Reject oversized declared bodies before CSRF/form parsing; Caddy caps streams."""
    MAX_BODY_BYTES = 6 * 1024 * 1024

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            length = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            return HttpResponse("Tamaño de solicitud no válido.", status=400)
        if length > self.MAX_BODY_BYTES:
            return HttpResponse("La solicitud supera el límite de 6 MB.", status=413)
        return self.get_response(request)
