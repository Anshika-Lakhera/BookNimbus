from django.db import models
from django.contrib.auth.hashers import make_password
from django.utils import timezone
import json


class Credentials(models.Model):
    UserID = models.AutoField(primary_key=True)
    UserName = models.CharField(max_length=150, unique=True)
    Email = models.EmailField(max_length=255, unique=True)
    Password = models.CharField(max_length=255, blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    is_author = models.BooleanField(default=False)
    author_completed = models.BooleanField(default=False)
    google_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    Read = models.JSONField(default=dict, blank=True)
    Currently_Reading = models.JSONField(default=dict, blank=True)
    Want_To_Read = models.JSONField(default=dict, blank=True)
    Following = models.JSONField(default=dict, blank=True)
    Followed = models.JSONField(default=dict, blank=True)
    bio = models.TextField(blank=True, null=True)
    profile_picture = models.URLField(max_length=1000, blank=True, null=True)
    followers_count = models.IntegerField(default=0)
    following_count = models.IntegerField(default=0)

    class Meta:
        db_table = 'Credentials'
        managed = False

    def __str__(self):
        return self.UserName

    def save(self, *args, **kwargs):
        # Ensure JSON fields are never None
        if self.Read is None:
            self.Read = {}
        if self.Currently_Reading is None:
            self.Currently_Reading = {}
        if self.Want_To_Read is None:
            self.Want_To_Read = {}
        if self.Following is None:
            self.Following = {}
        if self.Followed is None:
            self.Followed = {}

        # Update counts from JSON data to ensure they're always correct
        self.following_count = len(self.Following)
        self.followers_count = len(self.Followed)

        super().save(*args, **kwargs)

    def get_reading_status(self):
        return {
            'read': self.Read or {},
            'currently_reading': self.Currently_Reading or {},
            'want_to_read': self.Want_To_Read or {}
        }

    def update_reading_status(self, book_id, book_data, status):
        book_id_str = str(book_id)

        # Remove book from all statuses
        if self.Read:
            self.Read.pop(book_id_str, None)
        if self.Currently_Reading:
            self.Currently_Reading.pop(book_id_str, None)
        if self.Want_To_Read:
            self.Want_To_Read.pop(book_id_str, None)

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
        if self.Read and book_id_str in self.Read:
            return 'read'
        elif self.Currently_Reading and book_id_str in self.Currently_Reading:
            return 'currently-reading'
        elif self.Want_To_Read and book_id_str in self.Want_To_Read:
            return 'want-to-read'
        return 'none'

    def follow_user(self, user_to_follow_id):
        user_to_follow_id_str = str(user_to_follow_id)

        if user_to_follow_id_str not in self.Following:
            try:
                user_to_follow = Credentials.objects.get(UserID=user_to_follow_id)
                self.Following[user_to_follow_id_str] = {
                    'followed_at': str(timezone.now()),
                    'username': user_to_follow.UserName
                }

                # Update the user being followed
                my_id_str = str(self.UserID)
                if my_id_str not in user_to_follow.Followed:
                    user_to_follow.Followed[my_id_str] = {
                        'followed_at': str(timezone.now()),
                        'username': self.UserName
                    }
                    user_to_follow.save()  # This will trigger the count update in save()

                self.save()  # This will trigger the count update in save()
                return True

            except Credentials.DoesNotExist:
                return False
        return True

    def unfollow_user(self, user_to_unfollow_id):
        user_to_unfollow_id_str = str(user_to_unfollow_id)

        if user_to_unfollow_id_str in self.Following:
            del self.Following[user_to_unfollow_id_str]

            try:
                user_to_unfollow = Credentials.objects.get(UserID=user_to_unfollow_id)
                my_id_str = str(self.UserID)
                if my_id_str in user_to_unfollow.Followed:
                    del user_to_unfollow.Followed[my_id_str]
                    user_to_unfollow.save()  # This will trigger the count update in save()
            except Credentials.DoesNotExist:
                pass

            self.save()  # This will trigger the count update in save()
            return True
        return False

    def is_following(self, user_id):
        return str(user_id) in (self.Following or {})

    def get_followers_count(self):
        # Always return the actual count from the database field
        return self.followers_count if self.followers_count is not None else 0

    def get_following_count(self):
        # Always return the actual count from the database field
        return self.following_count if self.following_count is not None else 0

    @classmethod
    def create_google_user(cls, google_id, email, username):
        user = cls(
            UserName=username,
            Email=email,
            google_id=google_id,
            is_verified=True,
            is_author=False,
            author_completed=False,
            Read={},
            Currently_Reading={},
            Want_To_Read={},
            Following={},
            Followed={},
            followers_count=0,
            following_count=0
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
    average_rating = models.FloatField(default=0.0)
    review_count = models.IntegerField(default=0)

    class Meta:
        db_table = 'Books'
        managed = False

    def __str__(self):
        return f"{self.title} by {self.author}"

    def to_dict(self):
        return {
            'BookID': self.bookid,
            'Title': self.title,
            'Author': self.author,
            'Genre': self.genre,
            'Year': self.year,
            'CoverURL': self.coverurl,
            'EpubURL': self.epub_url,
            'AverageRating': float(self.average_rating) if self.average_rating else 0.0,
            'ReviewCount': self.review_count or 0
        }

    @classmethod
    def get_all_books(cls):
        try:
            return cls.objects.all().order_by('title')
        except Exception as e:
            print(f"Error in get_all_books: {e}")
            return cls.objects.none()

    @classmethod
    def get_books_by_author(cls, author_name):
        try:
            return cls.objects.filter(author=author_name).order_by('title')
        except Exception as e:
            print(f"Error in get_books_by_author: {e}")
            return cls.objects.none()


class Reviews(models.Model):
    review_id = models.AutoField(primary_key=True)
    book = models.ForeignKey(Books, on_delete=models.CASCADE, db_column='book_id')
    user = models.ForeignKey(Credentials, on_delete=models.CASCADE, db_column='user_id')
    rating = models.IntegerField()
    review_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'Reviews'
        managed = False

    def __str__(self):
        return f"Review by {self.user.UserName} for {self.book.title}"

    def to_dict(self):
        return {
            'review_id': self.review_id,
            'book_id': self.book.bookid,
            'user_id': self.user.UserID,
            'username': self.user.UserName,
            'rating': self.rating,
            'review_text': self.review_text,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }


class Posts(models.Model):
    post_id = models.AutoField(primary_key=True)
    author = models.ForeignKey(Credentials, on_delete=models.CASCADE, db_column='author_id')
    title = models.CharField(max_length=500)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'Posts'
        managed = False

    def __str__(self):
        return f"Post by {self.author.UserName}: {self.title}"

    def to_dict(self):
        return {
            'post_id': self.post_id,
            'author_id': self.author.UserID,
            'author_name': self.author.UserName,
            'title': self.title,
            'content': self.content,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }