from django.contrib import admin
from django.urls import include, path

from chat.urls import api_urlpatterns

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("api/", include((api_urlpatterns, "chat_api"))),
    path("", include("chat.urls")),
]
