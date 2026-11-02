from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("audit-events", views.AuditEventViewSet, basename="audit-events")
router.register("support-grants", views.SupportGrantViewSet, basename="support-grants")

urlpatterns = router.urls
