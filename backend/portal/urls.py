from django.urls import path

from . import views

urlpatterns = [
    path("children/", views.ChildrenView.as_view(), name="portal-children"),
    path("children/<int:pk>/today/", views.ChildDayView.as_view(), name="portal-child-day"),
    path("children/<int:pk>/scores/", views.ChildScoresView.as_view(), name="portal-child-scores"),
]
