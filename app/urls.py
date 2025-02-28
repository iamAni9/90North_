from django.urls import path, include
from .views import *

urlpatterns = [
    path('accounts/', include('allauth.urls')),
    path('auth/google/login/', google_login, name='google_login'),
    path('auth/google/callback/', google_callback, name='google_callback'),
    
    path('auth/google/drive/connect/', connect_google_drive, name='connect_google_drive'),
    path('auth/google/drive/callback/', google_drive_callback, name='google_drive_callback'),
    path('upload/', upload_to_google_drive, name='upload_to_google_drive'),
    path('download/<str:file_id>/', download_from_google_drive, name='download_from_google_drive'),
]
