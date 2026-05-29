"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.conf import settings
import os
from django.http import FileResponse, HttpResponse

def serve_react(request, *args, **kwargs):
    index_path = os.path.join(
        settings.BASE_DIR,
        'frontend',
        'build',
        'index.html'
    )

    if not os.path.exists(index_path):
        return HttpResponse("React build not found", status=500)

    with open(index_path, 'r') as f:
        return HttpResponse(f.read(), content_type='text/html')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('core.urls')),
    path('', serve_react),
    path('<path:path>', serve_react),
]