from django.db import models

class Credentials(models.Model):
    UserID = models.AutoField(primary_key=True)
    UserName = models.CharField(max_length=150, unique=True)
    Email = models.EmailField(max_length=255, unique=True)
    Password = models.CharField(max_length=255)
    is_verified = models.BooleanField(default=False)

    class Meta:
        db_table = 'Credentials'
        managed = False  # Supabase table exists

    def __str__(self):
        return self.UserName
