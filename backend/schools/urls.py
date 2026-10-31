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
}.items():
    router.register(prefix, viewset, basename=prefix)

urlpatterns = router.urls
