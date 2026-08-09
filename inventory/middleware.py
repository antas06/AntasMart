from django.conf import settings
from django.contrib.auth.views import redirect_to_login


class LoginRequiredMiddleware:
    """Require a signed-in user on every route except public receipts and login."""

    public_prefixes = ('/receipt/', '/accounts/login/', '/admin/', '/static/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            not request.user.is_authenticated
            and not request.path.startswith(self.public_prefixes)
        ):
            return redirect_to_login(request.get_full_path())
        return self.get_response(request)
