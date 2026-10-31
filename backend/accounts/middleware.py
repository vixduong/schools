from django.contrib.auth.models import AnonymousUser


class SchoolBoundUserMiddleware:
    """Django-level twin of SchoolSessionAuthentication: a session that was not created on this
    School's host (another School's, or none recorded) yields an anonymous `request.user`, so
    plain Django views, audit and telemetry never see the wrong person."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.session.get("school_id") != request.school.pk:
            request.user = AnonymousUser()
        return self.get_response(request)
