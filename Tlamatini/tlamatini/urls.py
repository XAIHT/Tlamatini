from django.contrib import admin
from django.urls import path, include
from agent.views import login_view # Import login_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('agent/', include('agent.urls')),
    path('', login_view, name='home'), # Add this line to handle the root URL
]