from django.urls import path

from . import views

app_name = "chat"

urlpatterns = [
    path("", views.index, name="index"),
]

api_urlpatterns = [
    path("users/", views.UserListAPIView.as_view(), name="api-users"),
    path("chat/<int:user_id>/messages/", views.MessageHistoryAPIView.as_view(), name="api-messages"),
    path("chat/<int:user_id>/read/", views.MarkReadAPIView.as_view(), name="api-mark-read"),
]
