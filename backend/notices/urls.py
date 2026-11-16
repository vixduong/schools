from django.urls import path

from . import views

urlpatterns = [
    path("notices/", views.NoticesView.as_view(), name="notices"),
    path("notices/audiences/", views.AudiencesView.as_view(), name="notice-audiences"),
    path("notices/<int:pk>/read/", views.NoticeReadView.as_view(), name="notice-read"),
]
