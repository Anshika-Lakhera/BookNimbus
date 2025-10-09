from django.db import models
from django.contrib.auth.hashers import make_password

class Credentials(models.Model):
    UserID = models.AutoField(primary_key=True)
    UserName = models.CharField(max_length=150, unique=True)
    Email = models.EmailField(max_length=255, unique=True)
    Password = models.CharField(max_length=255, blank=True, null=True)  # Make optional for Google users
    is_verified = models.BooleanField(default=False)
    google_id = models.CharField(max_length=255, blank=True, null=True, unique=True)  # Add this field
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'Credentials'
        managed = False  # Supabase table exists

    def __str__(self):
        return self.UserName

    @classmethod
    def create_google_user(cls, google_id, email, username):
        """Create a user from Google authentication"""
        user = cls(
            UserName=username,
            Email=email,
            google_id=google_id,
            is_verified=True  # Google emails are verified
        )
        # We don't set password for Google users
        user.save()
        return user