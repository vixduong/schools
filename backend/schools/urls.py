from django.urls import re_path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
for prefix, viewset in {
    "school-years": views.SchoolYearViewSet,
    "terms": views.TermViewSet,
    "levels": views.LevelViewSet,
    "grades": views.GradeViewSet,
    "subject-groups": views.SubjectGroupViewSet,
    "subjects": views.SubjectViewSet,
    "rooms": views.RoomViewSet,
    "classes": views.SchoolClassViewSet,
    "role-assignments": views.RoleAssignmentViewSet,
    "students": views.StudentViewSet,
    "enrollments": views.EnrollmentViewSet,
    "guardian-links": views.GuardianLinkViewSet,
    "assessment-profiles": views.AssessmentProfileViewSet,
    "memberships": views.MembershipViewSet,
    "invitations": views.InvitationViewSet,
    "imports": views.ImportViewSet,
}.items():
    router.register(prefix, viewset, basename=prefix)

urlpatterns = [
    re_path(
        r"^imports/templates/(?P<kind>staff|students|guardians)\.xlsx$",
        views.ImportViewSet.as_view({"get": "template"}),
        name="import-template",
    ),
    *router.urls,
]
