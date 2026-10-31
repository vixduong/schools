from django.conf import settings
from django.http import Http404

from .models import School
from .rls import school_scope


class TenantMiddleware:
    """Resolve the School from `<subdomain>.<BASE_DOMAIN>` and run the rest of the request in a
    transaction scoped to it. Responses must not stream DB data: a streaming body is consumed
    after the transaction (and the GUC) is gone."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(":")[0].lower()
        suffix = "." + settings.BASE_DOMAIN
        if not host.endswith(suffix):
            raise Http404
        school = School.objects.filter(subdomain=host.removesuffix(suffix)).first()
        if school is None:
            raise Http404
        request.school = school
        with school_scope(school.pk):
            return self.get_response(request)
