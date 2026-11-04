from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("bell-periods", views.BellPeriodViewSet, basename="bell-periods")

urlpatterns = [
    path("classes/<int:pk>/timetable/", views.ClassTimetableView.as_view(), name="class-timetable"),
    path(
        "attendance/<int:entry>/<str:on>/",
        views.PeriodAttendanceView.as_view(),
        name="period-attendance",
    ),
    path(
        "classes/<int:pk>/attendance/",
        views.ClassAttendanceView.as_view(),
        name="class-attendance",
    ),
    path("timetable/mine/", views.MyTimetableView.as_view(), name="my-timetable"),
    *router.urls,
]
