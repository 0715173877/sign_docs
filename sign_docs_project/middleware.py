from django.utils.cache import add_never_cache_headers
from django.shortcuts import redirect
from django.urls import reverse


class NoCacheMiddleware:
    """
    Middleware that adds Cache-Control: no-cache, no-store, must-revalidate
    headers to all responses for authenticated users.
    
    This prevents the browser from caching pages that require login,
    so clicking the "back" button after logout won't show cached pages.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Only add no-cache headers for authenticated users
        # (login page and public pages should still be cacheable)
        if request.user.is_authenticated:
            add_never_cache_headers(response)

        return response


class PendingOTPMiddleware:
    """
    Middleware that blocks users who have logged in but haven't verified
    their OTP yet from accessing protected pages.
    
    After login_view validates credentials, it sets pending_otp=True in the
    session. The user must verify their OTP on the login_otp page before
    they can access any other authenticated pages.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check if user has a pending OTP (logged in but not verified)
        if request.session.get('pending_otp'):
            # Allow access only to the login OTP page and logout
            allowed_paths = [
                reverse('login_otp'),
                reverse('logout'),
            ]
            # Also allow the login page itself (in case they want to go back)
            allowed_paths.append(reverse('login'))

            if request.path not in allowed_paths:
                return redirect('login_otp')

        response = self.get_response(request)
        return response
