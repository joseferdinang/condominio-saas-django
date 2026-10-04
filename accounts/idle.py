"""Inactivity protection shared by portal and Django Admin sessions."""

import time

from django.conf import settings
from django.contrib.auth import logout
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.cache import patch_cache_control
from django.views.decorators.http import require_POST

ACTIVITY_KEY = "last_user_activity"


class IdleSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Health checks and static resources must not keep a session alive.
        ignored = request.path == "/health/" or request.path.startswith(
            (settings.STATIC_URL, settings.MEDIA_URL)
        )
        if request.user.is_authenticated and not ignored:
            now = time.time()
            last = request.session.get(ACTIVITY_KEY, now)
            if not isinstance(last, (int, float)) or now - last >= settings.SESSION_IDLE_TIMEOUT:
                logout(request)
                login_url = reverse("accounts:login") + "?inactivo=1"
                if request.path == reverse("accounts:session_activity"):
                    return JsonResponse({"expired": True}, status=401)
                if request.headers.get("HX-Request") == "true":
                    return HttpResponse(headers={"HX-Redirect": login_url})
                return redirect(login_url)
            request.session[ACTIVITY_KEY] = now
            request.session.set_expiry(settings.SESSION_IDLE_TIMEOUT)

        response = self.get_response(request)
        # Django's LoginView authenticates during the view, after our first check.
        if request.user.is_authenticated and ACTIVITY_KEY not in request.session and not ignored:
            request.session[ACTIVITY_KEY] = time.time()
            request.session.set_expiry(settings.SESSION_IDLE_TIMEOUT)
        if request.user.is_authenticated and not ignored:
            patch_cache_control(response, private=True, no_store=True)
        return response


@require_POST
def session_activity(request):
    """Refresh an existing authenticated session after browser interaction."""
    if not request.user.is_authenticated:
        return JsonResponse({"expired": True}, status=401)
    return JsonResponse({"timeout": settings.SESSION_IDLE_TIMEOUT})


def idle_session_context(request):
    if not request.user.is_authenticated:
        return {}
    remaining = settings.SESSION_IDLE_TIMEOUT - (
        time.time() - request.session.get(ACTIVITY_KEY, time.time())
    )
    return {"session_idle_remaining_ms": max(0, int(remaining * 1000))}
