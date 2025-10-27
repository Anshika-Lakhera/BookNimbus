# models.py
from django.db import models
from django.contrib.auth.hashers import make_password
import json


class Credentials(models.Model):
    UserID = models.AutoField(primary_key=True)
    UserName = models.CharField(max_length=150, unique=True)
    Email = models.EmailField(max_length=255, unique=True)
    Password = models.CharField(max_length=255, blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    is_author = models.BooleanField(default=False)
    author_completed = models.BooleanField(default=False)  # NEW FIELD
    google_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    Read = models.JSONField(default=dict, blank=True)
    Currently_Reading = models.JSONField(default=dict, blank=True)
    Want_To_Read = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'Credentials'
        managed = False

    def __str__(self):
        return self.UserName

    def get_reading_status(self):
        return {
            'read': self.Read,
            'currently_reading': self.Currently_Reading,
            'want_to_read': self.Want_To_Read
        }

    def update_reading_status(self, book_id, book_data, status):
        book_id_str = str(book_id)

        # Remove book from all statuses first
        self.Read.pop(book_id_str, None)
        self.Currently_Reading.pop(book_id_str, None)
        self.Want_To_Read.pop(book_id_str, None)

        # Add to the new status if not 'none'
        if status != 'none':
            if status == 'read':
                self.Read[book_id_str] = book_data
            elif status == 'currently-reading':
                self.Currently_Reading[book_id_str] = book_data
            elif status == 'want-to-read':
                self.Want_To_Read[book_id_str] = book_data

        self.save()
        return True

    def get_book_status(self, book_id):
        book_id_str = str(book_id)
        if book_id_str in self.Read:
            return 'read'
        elif book_id_str in self.Currently_Reading:
            return 'currently-reading'
        elif book_id_str in self.Want_To_Read:
            return 'want-to-read'
        return 'none'

    @classmethod
    def create_google_user(cls, google_id, email, username):
        user = cls(
            UserName=username,
            Email=email,
            google_id=google_id,
            is_verified=True,
            is_author=False,
            author_completed=False,  # NEW
            Read={},
            Currently_Reading={},
            Want_To_Read={}
        )
        user.save()
        return user


class Books(models.Model):
    bookid = models.AutoField(primary_key=True)
    title = models.CharField(max_length=500)
    author = models.CharField(max_length=300)
    genre = models.CharField(max_length=200)
    year = models.IntegerField()
    coverurl = models.URLField(max_length=1000, blank=True, null=True)
    epub_url = models.URLField(max_length=1000, blank=True, null=True)

    class Meta:
        db_table = 'Books'
        managed = False

    def __str__(self):
        return f"{self.title} by {self.author}"

    def to_dict(self):
        """Convert book instance to dictionary for JSON serialization"""
        return {
            'BookID': self.bookid,
            'Title': self.title,
            'Author': self.author,
            'Genre': self.genre,
            'Year': self.year,
            'CoverURL': self.coverurl,
            'EpubURL': self.epub_url
        }

    @classmethod
    def get_all_books(cls):
        """Get all books ordered by title"""
        try:
            return cls.objects.all().order_by('title')
        except Exception as e:
            print(f"Error in get_all_books: {e}")
            return cls.objects.none()

    @classmethod
    def get_books_by_author(cls, author_name):
        """Get books by specific author"""
        try:
            return cls.objects.filter(author=author_name).order_by('title')
        except Exception as e:
            print(f"Error in get_books_by_author: {e}")
            return cls.objects.none()