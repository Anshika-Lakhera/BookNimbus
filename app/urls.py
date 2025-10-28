from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('shelves/', views.shelves, name='shelves'),
    path('', views.index, name='index'),
    path('home/', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('verify-email/', views.verify_email, name='verify_email'),
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('reset-password-page/', views.reset_password_page, name='reset_password_page'),
    path('reset-password/', views.reset_password, name='reset_password'),
    path('logout/', views.logout_view, name='logout'),
    path('author-create/', views.author_create, name='author_create'),
    path('author-books/', views.author_books, name='author_books'),  # NEW
    path('create-post/', views.create_post, name='create_post'),     # NEW
    path('debug-email/', views.debug_email_config, name='debug_email'),

    # API endpoints for reading status
    path('api/update-reading-status/', views.update_reading_status, name='update_reading_status'),
    path('api/reading-status/<int:user_id>/', views.get_reading_status, name='get_reading_status'),
    path('api/user-stats/<int:user_id>/', views.get_user_stats, name='get_user_stats'),

    # Books API endpoint
    path('api/books/', views.get_books, name='get_books'),
    path('epub-reader/', views.epub_reader, name='epub_reader'),

    # Google OAuth URLs
    path('google-auth/', views.google_auth_init, name='google_auth'),
    path('google-callback/', views.google_callback, name='google_callback'),
]

# Serve static files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
