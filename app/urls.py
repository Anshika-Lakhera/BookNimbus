from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index, name='index'),
    path('home/', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('verify-email/', views.verify_email, name='verify_email'),
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('reset-password-page/', views.reset_password_page, name='reset_password_page'),
    path('reset-password/', views.reset_password, name='reset_password'),
    path('logout/', views.logout_view, name='logout'),

    # Google OAuth URLs
    path('google-auth/', views.google_auth_init, name='google_auth'),
    path('google-callback/', views.google_callback, name='google_callback'),
]

# Serve static files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
