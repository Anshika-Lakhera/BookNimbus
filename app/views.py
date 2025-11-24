import json
import requests
import uuid
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.hashers import make_password, check_password
from django.core.mail import send_mail
from django.utils.crypto import get_random_string
from django.conf import settings
import os
from django.views.decorators.http import require_http_methods
from .models import Credentials, Books, Reviews, Posts
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils import timezone
from django.db import connection, transaction
from django.contrib.auth.decorators import login_required
import logging

logger = logging.getLogger(__name__)

verification_tokens = {}
password_reset_tokens = {}

GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID',
                                  '1098327710097-5mqs9s1linj3rqck41phtl7ibh18u5ra.apps.googleusercontent.com')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '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')
GOOGLE_REDIRECT_URI = os.environ.get('GOOGLE_REDIRECT_URI', 'http://127.0.0.1:8000/google-callback/')

SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://arwnfwtjpjhegtgdrpmi.supabase.co')
SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_KEY',
                                      'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFyd25md3RqcGpoZWd0Z2RycG1pIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MDAxMzkyMCwiZXhwIjoyMDc1NTg5OTIwfQ.FPYRFHub7dGv7zOuHitIbpcUYiVRd39WWuaK9vvD7pc')


def index(request):
    return render(request, 'index.html')


def get_next_book_id():
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval('books_bookid_seq')")
        row = cursor.fetchone()
        return row[0] if row else 1


def shelves(request):
    username = request.session.get('username')
    user_id = request.session.get('user_id')

    if not username:
        return redirect('index')

    if not user_id:
        try:
            user = Credentials.objects.get(UserName=username)
            user_id = user.UserID
            request.session['user_id'] = user_id
            request.session['is_author'] = user.is_author
            request.session['author_completed'] = user.author_completed
        except Credentials.DoesNotExist:
            return redirect('index')

    user_obj = Credentials.objects.get(UserID=user_id)
    if user_obj.is_author and not user_obj.author_completed:
        return redirect('author_create')

    print(f"DEBUG: Rendering shelves for user_id: {user_id}")

    return render(request, 'shelves.html', {
        'username': username,
        'user_id': user_id,
        'is_author': request.session.get('is_author', False),
        'author_completed': request.session.get('author_completed', False)
    })


@ensure_csrf_cookie
def author_create(request):
    username = request.session.get('username')
    user_id = request.session.get('user_id')

    if not username:
        return redirect('index')

    try:
        user = Credentials.objects.get(UserID=user_id)

        if user.author_completed:
            return redirect('home')

    except Credentials.DoesNotExist:
        return redirect('index')

    if request.method == 'POST':
        try:
            bio = request.POST.get('bio', '')
            profile_picture = request.FILES.get('profile_picture')

            user.is_author = True
            user.author_completed = True
            user.bio = bio

            if profile_picture:
                profile_filename = f"profile_{uuid.uuid4()}{os.path.splitext(profile_picture.name)[1]}"
                profile_url = upload_to_supabase(profile_picture, 'profiles', profile_filename)
                if profile_url:
                    user.profile_picture = profile_url

            user.save(update_fields=['is_author', 'author_completed', 'bio', 'profile_picture'])

            request.session['is_author'] = True
            request.session['author_completed'] = True

            return JsonResponse({
                'status': 'success',
                'message': 'Author profile created successfully!',
                'redirect': '/home/'
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': f'Error creating author profile: {str(e)}'
            }, status=500)

    return render(request, 'author_create.html', {
        'username': username,
        'user_id': user_id
    })


def author_books(request):
    author_name = request.GET.get('author', '')
    username = request.session.get('username')
    user_id = request.session.get('user_id')

    if not username:
        return redirect('index')

    try:
        current_user = Credentials.objects.get(UserID=user_id)
        author_user = Credentials.objects.get(UserName=author_name)

        books = Books.get_books_by_author(author_name)
        books_data = [book.to_dict() for book in books]

        # Get author's posts
        posts = Posts.objects.filter(author=author_user).order_by('-created_at')
        posts_data = [post.to_dict() for post in posts]

        is_following = current_user.is_following(author_user.UserID)

        followers_count = author_user.get_followers_count()
        following_count = author_user.get_following_count()
        books_count = books.count()
        posts_count = posts.count()

        author_bio = author_user.bio or 'No bio available yet.'
        author_photo_url = author_user.profile_picture or ''

        return render(request, 'author_books.html', {
            'username': username,
            'user_id': user_id,
            'author_name': author_name,
            'books': books_data,
            'posts': posts_data,
            'is_author': request.session.get('is_author', False),
            'author_completed': request.session.get('author_completed', False),
            'is_following': is_following,
            'followers_count': followers_count,
            'following_count': following_count,
            'books_count': books_count,
            'posts_count': posts_count,
            'author_bio': author_bio,
            'author_photo_url': author_photo_url,
            'author_user_id': author_user.UserID,
        })

    except Credentials.DoesNotExist:
        return render(request, 'error.html', {'message': 'Author not found'})


@require_http_methods(["GET"])
def get_books(request):
    try:
        author_filter = request.GET.get('author', None)

        if author_filter:
            books_queryset = Books.get_books_by_author(author_filter)
        else:
            books_queryset = Books.get_all_books()

        books_data = [book.to_dict() for book in books_queryset]

        if books_data:
            return JsonResponse({
                'success': True,
                'books': books_data
            })
        else:
            return JsonResponse({
                'success': True,
                'books': [],
                'message': 'No books found'
            })

    except Exception as e:
        print(f"Error fetching books: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


def epub_reader(request):
    return render(request, 'epub_reader.html')


def home(request):
    username = request.session.get('username')
    user_id = request.session.get('user_id')

    if not username:
        return redirect('index')

    if not user_id:
        try:
            user = Credentials.objects.get(UserName=username)
            user_id = user.UserID
            request.session['user_id'] = user_id
            request.session['is_author'] = user.is_author
            request.session['author_completed'] = user.author_completed
        except Credentials.DoesNotExist:
            return redirect('index')

    try:
        user_obj = Credentials.objects.get(UserID=user_id)
        if user_obj.is_author and not user_obj.author_completed:
            print(f"🔄 User {username} needs author creation, redirecting...")
            return redirect('author_create')
    except Credentials.DoesNotExist:
        return redirect('index')

    current_user = Credentials.objects.get(UserID=user_id)
    followers_count = current_user.get_followers_count()
    following_count = current_user.get_following_count()

    return render(request, 'home.html', {
        'username': username,
        'user_id': user_id,
        'is_author': request.session.get('is_author', False),
        'author_completed': request.session.get('author_completed', False),
        'followers_count': followers_count,
        'following_count': following_count
    })


@csrf_exempt
@require_http_methods(["POST"])
def update_reading_status(request):
    try:
        data = json.loads(request.body)
        user_id = data.get('user_id')
        book_id = data.get('book_id')
        status = data.get('status')
        book_data = data.get('book_data', {})

        if not all([user_id, book_id, status]):
            return JsonResponse({'error': 'Missing required fields'}, status=400)

        try:
            user = Credentials.objects.get(UserID=user_id)
            user.update_reading_status(book_id, book_data, status)

            return JsonResponse({
                'success': True,
                'message': 'Reading status updated successfully',
                'stats': {
                    'want_to_read': len(user.Want_To_Read or {}),
                    'currently_reading': len(user.Currently_Reading or {}),
                    'read': len(user.Read or {})
                }
            })

        except Credentials.DoesNotExist:
            return JsonResponse({'error': 'User not found'}, status=404)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
def get_reading_status(request, user_id):
    try:
        print(f"DEBUG: Getting reading status for user_id: {user_id}")

        user = Credentials.objects.get(UserID=user_id)
        print(f"DEBUG: User found: {user.UserName}")

        reading_status = user.get_reading_status()
        print(f"DEBUG: Reading status: {reading_status}")

        return JsonResponse({
            'success': True,
            'reading_status': reading_status,
            'stats': {
                'want_to_read': len(reading_status['want_to_read']),
                'currently_reading': len(reading_status['currently_reading']),
                'read': len(reading_status['read'])
            }
        })

    except Credentials.DoesNotExist:
        print(f"DEBUG: User {user_id} not found")
        return JsonResponse({'error': 'User not found'}, status=404)
    except Exception as e:
        print(f"DEBUG: Error in get_reading_status: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
def get_user_stats(request, user_id):
    try:
        user = Credentials.objects.get(UserID=user_id)

        reading_status = user.get_reading_status()

        return JsonResponse({
            'success': True,
            'stats': {
                'want_to_read': len(reading_status['want_to_read']),
                'currently_reading': len(reading_status['currently_reading']),
                'read': len(reading_status['read'])
            }
        })

    except Credentials.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def create_post(request):
    username = request.session.get('username')
    user_id = request.session.get('user_id')

    if not username or not user_id:
        return JsonResponse({'status': 'error', 'message': 'Not authenticated'}, status=401)

    try:
        user = Credentials.objects.get(UserID=user_id)
        if not user.is_author:
            return JsonResponse({'status': 'error', 'message': 'Not an author'}, status=403)
    except Credentials.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'User not found'}, status=404)

    if request.method == 'GET':
        return render(request, 'create_post.html', {
            'username': username,
            'user_id': user_id,
            'is_author': True,
            'author_completed': user.author_completed
        })

    elif request.method == 'POST':
        try:
            # Check if it's a book post or regular post
            post_type = request.POST.get('post_type', 'book')
            print(f"Post type: {post_type}")
            print(f"POST data: {dict(request.POST)}")
            print(f"FILES data: {dict(request.FILES)}")

            if post_type == 'book':
                # Book creation logic
                title = request.POST.get('title', '').strip()
                author = request.POST.get('author', '').strip()
                genre = request.POST.get('genre', '').strip()
                year = request.POST.get('year', '').strip()
                cover_file = request.FILES.get('cover')
                epub_file = request.FILES.get('epub')

                print(f"Book data - Title: {title}, Author: {author}, Genre: {genre}, Year: {year}")
                print(f"Files - Cover: {cover_file}, EPUB: {epub_file}")

                if not all([title, author, genre, year]):
                    return JsonResponse({
                        'status': 'error',
                        'message': 'All text fields are required for book creation'
                    }, status=400)

                if not cover_file or not epub_file:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Both cover image and EPUB file are required for book creation'
                    }, status=400)

                # Validate file types
                if not cover_file.content_type.startswith('image/'):
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Cover must be an image file'
                    }, status=400)

                if not epub_file.name.lower().endswith('.epub'):
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Book must be in EPUB format'
                    }, status=400)

                cover_extension = os.path.splitext(cover_file.name)[1]
                epub_extension = os.path.splitext(epub_file.name)[1]

                cover_filename = f"cover_{uuid.uuid4()}{cover_extension}"
                epub_filename = f"book_{uuid.uuid4()}{epub_extension}"

                cover_url = upload_to_supabase(cover_file, 'Book-Covers', cover_filename)
                if not cover_url:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Failed to upload cover image'
                    }, status=500)

                epub_url = upload_to_supabase(epub_file, 'Books', epub_filename)
                if not epub_url:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Failed to upload EPUB file'
                    }, status=500)

                next_book_id = get_next_book_id()
                print(f"Next book ID from sequence: {next_book_id}")

                book = Books.objects.create(
                    bookid=next_book_id,
                    title=title,
                    author=author,
                    genre=genre,
                    year=int(year),
                    coverurl=cover_url,
                    epub_url=epub_url
                )

                print(f"✅ Book created successfully with ID: {book.bookid}")

                return JsonResponse({
                    'status': 'success',
                    'message': 'Book published successfully!',
                    'book_id': book.bookid
                })
            else:
                # Blog post creation
                title = request.POST.get('title', '').strip()
                content = request.POST.get('content', '').strip()

                print(f"Blog data - Title: '{title}', Content: '{content[:100]}...'")

                if not title:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Blog post title is required'
                    }, status=400)

                if not content:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Blog post content is required'
                    }, status=400)

                post = Posts.objects.create(
                    author=user,
                    title=title,
                    content=content
                )

                return JsonResponse({
                    'status': 'success',
                    'message': 'Blog post published successfully!',
                    'post_id': post.post_id
                })

        except Exception as e:
            print(f"❌ Error creating post: {e}")
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'status': 'error',
                'message': f'Error creating post: {str(e)}'
            }, status=500)


def upload_to_supabase(file, bucket_name, filename):
    try:
        # First, check if bucket exists and create if needed
        buckets_url = f"{SUPABASE_URL}/storage/v1/bucket"
        headers = {
            'Authorization': f'Bearer {SUPABASE_SERVICE_KEY}',
            'Content-Type': 'application/json'
        }

        # Try to create bucket if it doesn't exist
        try:
            create_bucket_data = {
                "name": bucket_name,
                "id": bucket_name,
                "public": True,
                "file_size_limit": 52428800,  # 50MB
                "allowed_mime_types": ["image/*", "application/epub+zip"]
            }
            bucket_response = requests.post(buckets_url, headers=headers, json=create_bucket_data)
            print(f"Bucket creation response: {bucket_response.status_code}")
        except Exception as bucket_error:
            print(f"Bucket creation attempt: {bucket_error}")

        # Now upload the file
        upload_url = f"{SUPABASE_URL}/storage/v1/object/{bucket_name}/{filename}"

        upload_headers = {
            'Authorization': f'Bearer {SUPABASE_SERVICE_KEY}',
            'Content-Type': file.content_type,
            'Cache-Control': 'no-cache'
        }

        file_data = file.read()

        print(f"Uploading to: {upload_url}")
        print(f"File size: {len(file_data)} bytes")
        print(f"Bucket: {bucket_name}")
        print(f"Filename: {filename}")
        print(f"Content-Type: {file.content_type}")

        response = requests.post(
            upload_url,
            headers=upload_headers,
            data=file_data
        )

        print(f"Supabase upload response: {response.status_code}")
        print(f"Response text: {response.text}")

        if response.status_code == 200:
            public_url = f"{SUPABASE_URL}/storage/v1/object/public/{bucket_name}/{filename}"
            print(f"✅ Upload successful: {public_url}")
            return public_url
        else:
            print(f"❌ Supabase upload error {response.status_code}: {response.text}")
            # Try fallback upload method
            return upload_to_supabase_fallback(file, bucket_name, filename)

    except Exception as e:
        print(f"❌ Error uploading to Supabase: {str(e)}")
        return None


def upload_to_supabase_fallback(file, bucket_name, filename):
    """Fallback upload method using different approach"""
    try:
        # Alternative upload method
        upload_url = f"{SUPABASE_URL}/storage/v1/object/{bucket_name}/{filename}"

        files = {
            'file': (filename, file, file.content_type)
        }

        headers = {
            'Authorization': f'Bearer {SUPABASE_SERVICE_KEY}',
        }

        # Reset file pointer
        file.seek(0)

        response = requests.post(upload_url, headers=headers, files=files)

        print(f"Fallback upload response: {response.status_code}")

        if response.status_code == 200:
            public_url = f"{SUPABASE_URL}/storage/v1/object/public/{bucket_name}/{filename}"
            print(f"✅ Fallback upload successful: {public_url}")
            return public_url
        else:
            print(f"❌ Fallback upload failed: {response.text}")
            return None

    except Exception as e:
        print(f"❌ Fallback upload error: {str(e)}")
        return None

@csrf_exempt
def google_auth_init(request):
    if request.method == 'POST':
        auth_url = (
            "https://accounts.google.com/o/oauth2/v2/auth?"
            f"client_id={GOOGLE_CLIENT_ID}&"
            "response_type=code&"
            f"redirect_uri={GOOGLE_REDIRECT_URI}&"
            "scope=openid%20email%20profile&"
            "access_type=offline&"
            "prompt=consent"
        )
        return JsonResponse({'auth_url': auth_url})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})


@csrf_exempt
def google_callback(request):
    code = request.GET.get('code')

    if not code:
        return render(request, 'auth_result.html', {
            'success': False,
            'message': 'Authentication failed: No authorization code received'
        })

    try:
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': GOOGLE_REDIRECT_URI,
        }

        token_response = requests.post(token_url, data=token_data)
        token_json = token_response.json()

        if 'error' in token_json:
            return render(request, 'auth_result.html', {
                'success': False,
                'message': f'Token exchange failed: {token_json["error"]}'
            })

        access_token = token_json['access_token']

        userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
        headers = {'Authorization': f'Bearer {access_token}'}
        userinfo_response = requests.get(userinfo_url, headers=headers)
        userinfo = userinfo_response.json()

        if 'error' in userinfo:
            return render(request, 'auth_result.html', {
                'success': False,
                'message': f'Failed to get user info: {userinfo["error"]}'
            })

        google_id = userinfo['id']
        email = userinfo['email']
        name = userinfo.get('name', '').replace(' ', '_')
        given_name = userinfo.get('given_name', '')

        if not name or name == '_':
            name = email.split('@')[0]

        user = Credentials.objects.filter(google_id=google_id).first()

        if not user:
            user = Credentials.objects.filter(Email=email).first()

            if user:
                user.google_id = google_id
                user.save(update_fields=['google_id'])
            else:
                base_username = name
                username = base_username
                counter = 1

                while Credentials.objects.filter(UserName=username).exists():
                    username = f"{base_username}_{counter}"
                    counter += 1

                user = Credentials.objects.create(
                    UserName=username,
                    Email=email,
                    google_id=google_id,
                    is_verified=True,
                    is_author=True,
                    author_completed=False,
                    Read={},
                    Currently_Reading={},
                    Want_To_Read={},
                    Following={},
                    Followed={},
                    followers_count=0,
                    following_count=0
                )

        request.session['username'] = user.UserName
        request.session['user_id'] = user.UserID
        request.session['is_author'] = user.is_author
        request.session['author_completed'] = user.author_completed
        request.session['is_google_user'] = True

        print(f"🔍 GOOGLE USER STATUS: is_author={user.is_author}, author_completed={user.author_completed}")

        if user.is_author and not user.author_completed:
            print(f"🔄 Redirecting Google user {user.UserName} to author creation")
            return render(request, 'auth_result.html', {
                'success': True,
                'message': f'Welcome, {user.UserName}!',
                'redirect_url': '/author-create/'
            })
        else:
            print(f"🔄 Redirecting Google user {user.UserName} to home")
            return render(request, 'auth_result.html', {
                'success': True,
                'message': f'Welcome, {user.UserName}!',
                'redirect_url': '/home/'
            })

    except Exception as e:
        print(f"✗ GOOGLE AUTH ERROR: {e}")
        return render(request, 'auth_result.html', {
            'success': False,
            'message': 'Authentication failed. Please try again.'
        })


@csrf_exempt
def login_view(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            username = data.get('username')
            password = data.get('password')

            user = Credentials.objects.filter(UserName=username).first()

            if not user:
                return JsonResponse({'status': 'error', 'message': 'Invalid username or password'}, status=401)

            if not check_password(password, user.Password):
                return JsonResponse({'status': 'error', 'message': 'Invalid username or password'}, status=401)

            request.session['username'] = username
            request.session['user_id'] = user.UserID
            request.session['is_author'] = user.is_author
            request.session['author_completed'] = user.author_completed

            return JsonResponse({
                'status': 'success',
                'message': f'Welcome back, {username}!',
                'redirect': '/home/',
                'is_author': user.is_author
            })

        except Exception as e:
            print(f"✗ LOGIN ERROR: {e}")
            return JsonResponse({'status': 'error', 'message': 'Error during login'}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)


def verify_email(request):
    try:
        token = request.GET.get('token')
        if not token:
            logger.warning("Email verification attempted without token")
            return render(request, 'verify_result.html', {
                'success': False,
                'message': 'No verification token provided'
            })

        logger.debug(f"Processing verification token: {token[:8]}...")

        user_id = verification_tokens.get(token)
        if not user_id:
            logger.warning(f"Invalid or expired verification token: {token[:8]}...")
            return render(request, 'verify_result.html', {
                'success': False,
                'message': 'Invalid or expired verification token'
            })

        logger.debug(f"Token valid, looking up user ID: {user_id}")
        user = Credentials.objects.filter(UserID=user_id).first()

        if not user:
            logger.error(f"User not found for valid token. UserID: {user_id}, Token: {token[:8]}...")
            return render(request, 'verify_result.html', {
                'success': False,
                'message': 'User account not found'
            })

        user.is_verified = True
        user.save(update_fields=['is_verified'])
        logger.info(f"User {user_id} successfully verified email")

        del verification_tokens[token]
        logger.debug(f"Verification token {token[:8]}... removed from storage")

        request.session['username'] = user.UserName
        request.session['user_id'] = user.UserID
        request.session['is_author'] = user.is_author
        request.session['author_completed'] = user.author_completed
        logger.debug(f"Session updated for user {user_id}")

        if user.is_author and not user.author_completed:
            logger.info(f"Author user {user_id} needs profile completion, redirecting to author creation")
            return render(request, 'verify_result.html', {
                'success': True,
                'message': 'Email verified successfully! Setting up your author profile...',
                'redirect_url': '/author-create/'
            })
        else:
            logger.info(f"Regular user {user_id} verified, redirecting to home")
            return render(request, 'verify_result.html', {
                'success': True,
                'message': 'Email verified successfully!',
                'redirect_url': '/home/'
            })

    except Exception as e:
        logger.error(f"Unexpected error during email verification: {str(e)}", exc_info=True)
        return render(request, 'verify_result.html', {
            'success': False,
            'message': 'An unexpected error occurred during verification'
        })


@csrf_exempt
def signup_view(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            username = data.get('username')
            email = data.get('email')
            password = data.get('password')
            confirm_password = data.get('confirm_password')

            print(f"=== SIGNUP ATTEMPT: {username}, {email} ===")

            if not username or not password or not email:
                return JsonResponse({'status': 'error', 'message': 'All fields required'}, status=400)

            if len(username) < 3:
                return JsonResponse({'status': 'error', 'message': 'Username must be at least 3 characters'},
                                    status=400)

            if len(password) < 6:
                return JsonResponse({'status': 'error', 'message': 'Password must be at least 6 characters'},
                                    status=400)

            if password != confirm_password:
                return JsonResponse({'status': 'error', 'message': 'Passwords do not match'}, status=400)

            if Credentials.objects.filter(UserName=username).exists():
                return JsonResponse({'status': 'error', 'message': 'Username already exists'}, status=400)

            if Credentials.objects.filter(Email=email).exists():
                return JsonResponse({'status': 'error', 'message': 'Email already registered'}, status=400)

            hashed_password = make_password(password)
            user = Credentials.objects.create(
                UserName=username,
                Password=hashed_password,
                Email=email,
                is_verified=True,
                is_author=True,
                author_completed=False,
                Read={},
                Currently_Reading={},
                Want_To_Read={},
                Following={},
                Followed={},
                followers_count=0,
                following_count=0
            )

            print(f"✅ User created: {username} (ID: {user.UserID})")

            request.session['username'] = username
            request.session['user_id'] = user.UserID
            request.session['is_author'] = True
            request.session['author_completed'] = False

            return JsonResponse({
                'status': 'success',
                'message': 'Account created successfully! You can now login.',
                'redirect': '/home/'
            })

        except Exception as e:
            print(f"❌ SIGNUP ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'status': 'error',
                'message': 'An error occurred during signup. Please try again.'
            }, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)


@csrf_exempt
def forgot_password(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            email = data.get('email')

            if not email:
                return JsonResponse({'status': 'error', 'message': 'Email required'}, status=400)

            user = Credentials.objects.filter(Email=email).first()
            if not user:
                return JsonResponse({'status': 'error', 'message': 'No account found with this email'}, status=404)

            if user.google_id:
                return JsonResponse({
                    'status': 'error',
                    'message': 'This account uses Google authentication. Please sign in with Google.'
                }, status=400)

            base_url = 'https://book-nimbus.onrender.com'

            token = get_random_string(32)
            password_reset_tokens[token] = user.UserID
            reset_link = f"{base_url}/reset-password-page/?token={token}"

            try:
                send_mail(
                    'Reset your BookNimbus password',
                    f'Hi {user.UserName},\n\nYou requested to reset your password.\n\nClick the link below to reset:\n{reset_link}\n\nThis link will expire in 1 hour.\n\nIf you didn\'t request this, please ignore this email.',
                    'noreply@booknimbus.com',
                    [email],
                    fail_silently=False,
                )
                print(f"✅ Password reset email sent to {email}")
            except Exception as email_error:
                print(f"❌ EMAIL ERROR: {email_error}")
                import traceback
                traceback.print_exc()
                return JsonResponse({
                    'status': 'error',
                    'message': 'Error sending reset email. Please try again later.'
                }, status=500)

            return JsonResponse({
                'status': 'success',
                'message': 'Password reset link sent to your email'
            })

        except Exception as e:
            print(f"✗ FORGOT PASSWORD ERROR: {e}")
            import traceback
            traceback.print_exc()
            return JsonResponse({'status': 'error', 'message': 'Error sending reset email'}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)


def reset_password_page(request):
    token = request.GET.get('token')
    if not token or token not in password_reset_tokens:
        return render(request, 'reset_password.html', {
            'valid_token': False,
            'message': 'Invalid or expired reset link'
        })

    return render(request, 'reset_password.html', {
        'valid_token': True,
        'token': token
    })


@csrf_exempt
def reset_password(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            token = data.get('token')
            new_password = data.get('password')
            confirm_password = data.get('confirm_password')

            if not token or not new_password:
                return JsonResponse({'status': 'error', 'message': 'Token and password required'}, status=400)

            if len(new_password) < 6:
                return JsonResponse({'status': 'error', 'message': 'Password must be at least 6 characters'},
                                    status=400)

            if new_password != confirm_password:
                return JsonResponse({'status': 'error', 'message': 'Passwords do not match'}, status=400)

            user_id = password_reset_tokens.get(token)
            if not user_id:
                return JsonResponse({'status': 'error', 'message': 'Invalid or expired token'}, status=400)

            user = Credentials.objects.filter(UserID=user_id).first()
            if user:
                user.Password = make_password(new_password)
                user.save(update_fields=['Password'])
                del password_reset_tokens[token]

                return JsonResponse({
                    'status': 'success',
                    'message': 'Password updated successfully! You can now login.'
                })

            return JsonResponse({'status': 'error', 'message': 'User not found'}, status=404)

        except Exception as e:
            print(f"✗ RESET PASSWORD ERROR: {e}")
            return JsonResponse({'status': 'error', 'message': 'Error resetting password'}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)


def logout_view(request):
    request.session.flush()
    return redirect('index')


@csrf_exempt
def toggle_follow(request, author_name):
    if request.method == 'POST':
        try:
            # Get current user from session
            username = request.session.get('username')
            if not username:
                return JsonResponse({'status': 'error', 'message': 'Not authenticated'}, status=401)

            current_user = Credentials.objects.get(UserName=username)
            author_user = Credentials.objects.get(UserName=author_name)

            data = json.loads(request.body)
            action = data.get('action')

            if action == 'follow':
                success = current_user.follow_user(author_user.UserID)
                if success:
                    return JsonResponse({
                        'status': 'success',
                        'message': f'Now following {author_name}',
                        'action': 'followed',
                        'followers_count': author_user.get_followers_count()
                    })
                else:
                    return JsonResponse({'status': 'error', 'message': 'Failed to follow user'})
            elif action == 'unfollow':
                success = current_user.unfollow_user(author_user.UserID)
                if success:
                    return JsonResponse({
                        'status': 'success',
                        'message': f'Unfollowed {author_name}',
                        'action': 'unfollowed',
                        'followers_count': author_user.get_followers_count()
                    })
                else:
                    return JsonResponse({'status': 'error', 'message': 'Failed to unfollow user'})
            else:
                return JsonResponse({'status': 'error', 'message': 'Invalid action'})

        except Credentials.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'User not found'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})


@csrf_exempt
def check_follow_status(request, author_name):
    try:
        # Get current user from session
        username = request.session.get('username')
        if not username:
            return JsonResponse({'status': 'error', 'message': 'Not authenticated'}, status=401)

        current_user = Credentials.objects.get(UserName=username)
        author_user = Credentials.objects.get(UserName=author_name)

        is_following = current_user.is_following(author_user.UserID)

        return JsonResponse({
            'status': 'success',
            'is_following': is_following,
            'followers_count': author_user.get_followers_count()
        })

    except Credentials.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'User not found'})


@csrf_exempt
def edit_bio(request):
    username = request.session.get('username')
    user_id = request.session.get('user_id')

    if not username or not user_id:
        return JsonResponse({'status': 'error', 'message': 'Not authenticated'}, status=401)

    if request.method == 'POST':
        try:
            user = Credentials.objects.get(UserID=user_id)
            bio = request.POST.get('bio', '')
            profile_picture = request.FILES.get('profile_picture')

            user.bio = bio

            if profile_picture:
                profile_filename = f"profile_{uuid.uuid4()}{os.path.splitext(profile_picture.name)[1]}"
                profile_url = upload_to_supabase(profile_picture, 'profiles', profile_filename)
                if profile_url:
                    user.profile_picture = profile_url

            user.save(update_fields=['bio', 'profile_picture'])

            return JsonResponse({
                'status': 'success',
                'message': 'Profile updated successfully!'
            })

        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': f'Error updating profile: {str(e)}'
            }, status=500)

    return render(request, 'edit_bio.html', {
        'username': username,
        'user_id': user_id,
        'is_author': request.session.get('is_author', False),
        'author_completed': request.session.get('author_completed', False)
    })


@csrf_exempt
def get_follow_data(request):
    try:
        username = request.session.get('username')
        user_id = request.session.get('user_id')

        if not username or not user_id:
            return JsonResponse({'status': 'error', 'message': 'Not authenticated'}, status=401)

        user = Credentials.objects.get(UserID=user_id)

        followers_data = []
        following_data = []

        for user_id_str, data in (user.Followed or {}).items():
            try:
                follower_user = Credentials.objects.get(UserID=int(user_id_str))
                followers_data.append({
                    'username': follower_user.UserName,
                    'followed_at': data.get('followed_at', ''),
                    'profile_picture': follower_user.profile_picture or ''
                })
            except Credentials.DoesNotExist:
                continue

        for user_id_str, data in (user.Following or {}).items():
            try:
                following_user = Credentials.objects.get(UserID=int(user_id_str))
                following_data.append({
                    'username': following_user.UserName,
                    'followed_at': data.get('followed_at', ''),
                    'profile_picture': following_user.profile_picture or ''
                })
            except Credentials.DoesNotExist:
                continue

        return JsonResponse({
            'status': 'success',
            'followers': followers_data,
            'following': following_data,
            'followers_count': user.get_followers_count(),
            'following_count': user.get_following_count()
        })

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# Reviews functionality
@csrf_exempt
@require_http_methods(["POST"])
def add_review(request):
    try:
        data = json.loads(request.body)
        user_id = data.get('user_id')
        book_id = data.get('book_id')
        rating = data.get('rating')
        review_text = data.get('review_text', '')

        if not all([user_id, book_id, rating]):
            return JsonResponse({'error': 'Missing required fields'}, status=400)

        user = Credentials.objects.get(UserID=user_id)
        book = Books.objects.get(bookid=book_id)

        # Check if user already reviewed this book
        existing_review = Reviews.objects.filter(user=user, book=book).first()
        if existing_review:
            return JsonResponse({'error': 'You have already reviewed this book'}, status=400)

        # Create review
        review = Reviews.objects.create(
            user=user,
            book=book,
            rating=rating,
            review_text=review_text
        )

        # Update book ratings
        update_book_ratings(book)

        return JsonResponse({
            'status': 'success',
            'message': 'Review added successfully',
            'review': review.to_dict()
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
def get_reviews(request, book_id):
    try:
        reviews = Reviews.objects.filter(book_id=book_id).order_by('-created_at')
        reviews_data = [review.to_dict() for review in reviews]

        return JsonResponse({
            'status': 'success',
            'reviews': reviews_data
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def update_book_ratings(book):
    reviews = Reviews.objects.filter(book=book)
    if reviews.exists():
        average_rating = sum(review.rating for review in reviews) / reviews.count()
        book.average_rating = round(average_rating, 1)
        book.review_count = reviews.count()
        book.save()


# Blog posts functionality
@csrf_exempt
@require_http_methods(["POST"])
def create_blog_post(request):
    try:
        data = json.loads(request.body)
        user_id = data.get('user_id')
        title = data.get('title')
        content = data.get('content')

        if not all([user_id, title, content]):
            return JsonResponse({'error': 'Missing required fields'}, status=400)

        user = Credentials.objects.get(UserID=user_id)

        if not user.is_author:
            return JsonResponse({'error': 'Only authors can create blog posts'}, status=403)

        post = Posts.objects.create(
            author=user,
            title=title,
            content=content
        )

        return JsonResponse({
            'status': 'success',
            'message': 'Blog post created successfully',
            'post': post.to_dict()
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def debug_email_config(request):
    from django.conf import settings
    import os

    config_info = {
        'EMAIL_HOST': getattr(settings, 'EMAIL_HOST', 'NOT SET'),
        'EMAIL_PORT': getattr(settings, 'EMAIL_PORT', 'NOT SET'),
        'EMAIL_HOST_USER': getattr(settings, 'EMAIL_HOST_USER', 'NOT SET'),
        'DEFAULT_FROM_EMAIL': getattr(settings, 'DEFAULT_FROM_EMAIL', 'NOT SET'),
        'SENDGRID_API_KEY_IN_ENV': 'YES' if os.environ.get('SENDGRID_API_KEY') else 'NO',
        'SENDGRID_API_KEY_LENGTH': len(os.environ.get('SENDGRID_API_KEY', '')),
    }

    test_result = "Not attempted"
    try:
        from django.core.mail import send_mail
        send_mail(
            'BookNimbus Test Email',
            'This is a test email from BookNimbus.',
            settings.DEFAULT_FROM_EMAIL,
            [settings.DEFAULT_FROM_EMAIL],
            fail_silently=False,
        )
        test_result = "SUCCESS - Email sent"
    except Exception as e:
        test_result = f"FAILED - {str(e)}"

    config_info['TEST_EMAIL_RESULT'] = test_result

    return JsonResponse(config_info)

def author_books_detail(request, author_name):
    try:
        username = request.session.get('username')
        user_id = request.session.get('user_id')

        if not username:
            return redirect('index')

        current_user = Credentials.objects.get(UserID=user_id)
        author_user = Credentials.objects.get(UserName=author_name)

        books = Books.get_books_by_author(author_name)
        books_list = [book.to_dict() for book in books]

        # Get author's posts
        posts = Posts.objects.filter(author=author_user).order_by('-created_at')
        posts_data = [post.to_dict() for post in posts]

        is_following = current_user.is_following(author_user.UserID)

        followers_count = author_user.get_followers_count()
        following_count = author_user.get_following_count()
        books_count = books.count()
        posts_count = posts.count()

        author_bio = author_user.bio or 'No bio available yet.'
        author_photo_url = author_user.profile_picture or ''

        context = {
            'author_name': author_name,
            'books': books_list,
            'posts': posts_data,
            'username': username,
            'is_author': current_user.is_author,
            'author_completed': current_user.author_completed,
            'is_following': is_following,
            'followers_count': followers_count,
            'following_count': following_count,
            'books_count': books_count,
            'posts_count': posts_count,
            'author_bio': author_bio,
            'author_photo_url': author_photo_url,
            'author_user_id': author_user.UserID,
        }

        return render(request, 'author_books.html', context)

    except Credentials.DoesNotExist:
        return render(request, 'error.html', {'message': 'User not found'})

@require_http_methods(["GET"])
def get_author_posts(request, author_id):
    try:
        posts = Posts.objects.filter(author_id=author_id).order_by('-created_at')
        posts_data = [post.to_dict() for post in posts]

        return JsonResponse({
            'status': 'success',
            'posts': posts_data
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)