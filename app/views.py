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
from .models import Credentials, Books
from django.views.decorators.csrf import ensure_csrf_cookie

import logging

logger = logging.getLogger(__name__)


# In-memory tokens (for demo)
verification_tokens = {}
password_reset_tokens = {}

# Google OAuth2 Configuration - Use environment variables
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID',
                                  '1098327710097-5mqs9s1linj3rqck41phtl7ibh18u5ra.apps.googleusercontent.com')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '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')
GOOGLE_REDIRECT_URI = os.environ.get('GOOGLE_REDIRECT_URI', 'http://127.0.0.1:8000/google-callback/')

# Supabase Configuration
# Supabase Configuration
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://arwnfwtjpjhegtgdrpmi.supabase.co')
SUPABASE_ANON_KEY = os.environ.get('SUPABASE_ANON_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFyd25md3RqcGpoZWd0Z2RycG1pIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjAwMTM5MjAsImV4cCI6MjA3NTU4OTkyMH0.JUf22-Rt6LLnGjWULe4VZYNg_tH5aVlgclxx7JKL3yA')
SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFyd25md3RqcGpoZWd0Z2RycG1pIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MDAxMzkyMCwiZXhwIjoyMDc1NTg5OTIwfQ.FPYRFHub7dGv7zOuHitIbpcUYiVRd39WWuaK9vvD7pc')

def index(request):
    return render(request, 'index.html')

from django.db import connection

def get_next_book_id():
    """Get the next available bookid from the database sequence"""
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval('books_bookid_seq')")
        row = cursor.fetchone()
        return row[0] if row else 1


def shelves(request):
    """Shelves/Store page"""
    username = request.session.get('username')
    user_id = request.session.get('user_id')

    if not username:
        return redirect('index')

    # Ensure user_id is properly set
    if not user_id:
        try:
            user = Credentials.objects.get(UserName=username)
            user_id = user.UserID
            request.session['user_id'] = user_id
            request.session['is_author'] = user.is_author
            request.session['author_completed'] = user.author_completed
        except Credentials.DoesNotExist:
            return redirect('index')

    # Check if user needs author onboarding
    user_obj = Credentials.objects.get(UserID=user_id)
    if user_obj.is_author and not user_obj.author_completed:
        return redirect('author_create')

    # Debug output
    print(f"DEBUG: Rendering shelves for user_id: {user_id}")

    return render(request, 'shelves.html', {
        'username': username,
        'user_id': user_id,
        'is_author': request.session.get('is_author', False),
        'author_completed': request.session.get('author_completed', False)
    })


@ensure_csrf_cookie
def author_create(request):
    """Author profile creation page - sets is_author to True"""
    username = request.session.get('username')
    user_id = request.session.get('user_id')

    if not username:
        return redirect('index')

    # Get user object
    try:
        user = Credentials.objects.get(UserID=user_id)

        # If user is already completed author onboarding, redirect to home
        if user.author_completed:
            return redirect('home')

    except Credentials.DoesNotExist:
        return redirect('index')

    # If user submits author creation form
    if request.method == 'POST':
        try:
            user.is_author = True
            user.author_completed = True  # Mark as completed
            user.save(update_fields=['is_author', 'author_completed'])

            # Store in session
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
    """Show books by specific author"""
    author_name = request.GET.get('author', '')
    username = request.session.get('username')
    user_id = request.session.get('user_id')

    if not username:
        return redirect('index')

    # Get books by author
    books = Books.get_books_by_author(author_name)
    books_data = [book.to_dict() for book in books]

    return render(request, 'author_books.html', {
        'username': username,
        'user_id': user_id,
        'author_name': author_name,
        'books': books_data,
        'is_author': request.session.get('is_author', False),
        'author_completed': request.session.get('author_completed', False)
    })


@require_http_methods(["GET"])
def get_books(request):
    """Get books from database using Django model"""
    try:
        author_filter = request.GET.get('author', None)

        if author_filter:
            # Get books by specific author
            books_queryset = Books.get_books_by_author(author_filter)
        else:
            # Get all books
            books_queryset = Books.get_all_books()

        # Convert to list of dictionaries
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
    """EPUB Reader page"""
    return render(request, 'epub_reader.html')


def home(request):
    """Home screen after login"""
    username = request.session.get('username')
    user_id = request.session.get('user_id')

    if not username:
        return redirect('index')

    # If user_id is not in session, try to get it from the database
    if not user_id:
        try:
            user = Credentials.objects.get(UserName=username)
            user_id = user.UserID
            request.session['user_id'] = user_id
            request.session['is_author'] = user.is_author
            request.session['author_completed'] = user.author_completed
        except Credentials.DoesNotExist:
            return redirect('index')

    # Check if user needs author onboarding
    user_obj = Credentials.objects.get(UserID=user_id)
    if user_obj.is_author and not user_obj.author_completed:
        return redirect('author_create')

    return render(request, 'home.html', {
        'username': username,
        'user_id': user_id,
        'is_author': request.session.get('is_author', False),
        'author_completed': request.session.get('author_completed', False)
    })


@csrf_exempt
@require_http_methods(["POST"])
def update_reading_status(request):
    """Update reading status for a book"""
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
                    'want_to_read': len(user.Want_To_Read),
                    'currently_reading': len(user.Currently_Reading),
                    'read': len(user.Read)
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
    """Get all reading status for a user"""
    try:
        print(f"DEBUG: Getting reading status for user_id: {user_id}")

        user = Credentials.objects.get(UserID=user_id)
        print(f"DEBUG: User found: {user.UserName}")

        # Initialize None fields to empty dict
        if user.Read is None:
            user.Read = {}
        if user.Currently_Reading is None:
            user.Currently_Reading = {}
        if user.Want_To_Read is None:
            user.Want_To_Read = {}

        reading_status = user.get_reading_status()
        print(f"DEBUG: Reading status: {reading_status}")

        return JsonResponse({
            'success': True,
            'reading_status': reading_status,
            'stats': {
                'want_to_read': len(user.Want_To_Read),
                'currently_reading': len(user.Currently_Reading),
                'read': len(user.Read)
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
    """Get user reading statistics"""
    try:
        user = Credentials.objects.get(UserID=user_id)

        # Initialize None fields to empty dict
        if user.Read is None:
            user.Read = {}
        if user.Currently_Reading is None:
            user.Currently_Reading = {}
        if user.Want_To_Read is None:
            user.Want_To_Read = {}

        return JsonResponse({
            'success': True,
            'stats': {
                'want_to_read': len(user.Want_To_Read),
                'currently_reading': len(user.Currently_Reading),
                'read': len(user.Read)
            }
        })

    except Credentials.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def create_post(request):
    """Create new book post"""
    username = request.session.get('username')
    user_id = request.session.get('user_id')

    if not username or not user_id:
        return JsonResponse({'status': 'error', 'message': 'Not authenticated'}, status=401)

    # Check if user is author
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
            # Get form data
            title = request.POST.get('title')
            author = request.POST.get('author')
            genre = request.POST.get('genre')
            year = request.POST.get('year')
            cover_file = request.FILES.get('cover')
            epub_file = request.FILES.get('epub')

            # Validate required fields
            if not all([title, author, genre, year, cover_file, epub_file]):
                return JsonResponse({
                    'status': 'error',
                    'message': 'All fields are required'
                }, status=400)

            # Generate unique filenames
            cover_extension = os.path.splitext(cover_file.name)[1]
            epub_extension = os.path.splitext(epub_file.name)[1]

            cover_filename = f"cover_{uuid.uuid4()}{cover_extension}"
            epub_filename = f"book_{uuid.uuid4()}{epub_extension}"

            # Upload cover to Supabase
            cover_url = upload_to_supabase(cover_file, 'Book-Covers', cover_filename)
            if not cover_url:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Failed to upload cover image'
                }, status=500)

            # Upload EPUB to Supabase
            epub_url = upload_to_supabase(epub_file, 'Books', epub_filename)
            if not epub_url:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Failed to upload EPUB file'
                }, status=500)

            # Get next book ID from sequence
            def get_next_book_id():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT nextval('books_bookid_seq')")
                    row = cursor.fetchone()
                    return row[0] if row else 1

            next_book_id = get_next_book_id()
            print(f"Next book ID from sequence: {next_book_id}")

            # Create book in database with explicit ID
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

        except Exception as e:
            print(f"❌ Error creating post: {e}")
            return JsonResponse({
                'status': 'error',
                'message': f'Error creating post: {str(e)}'
            }, status=500)

def upload_to_supabase(file, bucket_name, filename):
    """Upload file to Supabase storage using service role key"""
    try:
        # Use service role key for bucket operations
        upload_url = f"{SUPABASE_URL}/storage/v1/object/{bucket_name}/{filename}"

        # Prepare headers with service role key
        headers = {
            'Authorization': f'Bearer {SUPABASE_SERVICE_KEY}',
            'Content-Type': file.content_type,
            'Cache-Control': 'no-cache'
        }

        # Read file data
        file_data = file.read()

        print(f"Uploading to: {upload_url}")
        print(f"File size: {len(file_data)} bytes")
        print(f"Bucket: {bucket_name}")
        print(f"Filename: {filename}")

        # Upload file using POST
        response = requests.post(
            upload_url,
            headers=headers,
            data=file_data
        )

        print(f"Supabase upload response: {response.status_code}")
        print(f"Response text: {response.text}")

        if response.status_code == 200:
            # Return public URL
            public_url = f"{SUPABASE_URL}/storage/v1/object/public/{bucket_name}/{filename}"
            print(f"✅ Upload successful: {public_url}")
            return public_url
        else:
            print(f"❌ Supabase upload error {response.status_code}: {response.text}")
            return None

    except Exception as e:
        print(f"❌ Error uploading to Supabase: {str(e)}")
        return None

@csrf_exempt
def google_auth_init(request):
    """Start Google OAuth flow"""
    if request.method == 'POST':
        # Generate Google OAuth URL
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
    """Handle Google OAuth callback"""
    code = request.GET.get('code')

    if not code:
        return render(request, 'auth_result.html', {
            'success': False,
            'message': 'Authentication failed: No authorization code received'
        })

    try:
        # Exchange code for tokens
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

        # Get user info from Google
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

        # Generate username if name not available
        if not name or name == '_':
            name = email.split('@')[0]

        # Check if user exists by google_id
        user = Credentials.objects.filter(google_id=google_id).first()

        if not user:
            # Check if user exists by email (for existing users linking Google)
            user = Credentials.objects.filter(Email=email).first()

            if user:
                # Link existing account with Google
                user.google_id = google_id
                user.save(update_fields=['google_id'])
            else:
                # Create new user with Google
                base_username = name
                username = base_username
                counter = 1

                # Ensure unique username
                while Credentials.objects.filter(UserName=username).exists():
                    username = f"{base_username}_{counter}"
                    counter += 1

                user = Credentials.objects.create(
                    UserName=username,
                    Email=email,
                    google_id=google_id,
                    is_verified=True,
                    is_author=False,
                    author_completed=False,
                    Read={},
                    Currently_Reading={},
                    Want_To_Read={}
                )

        # Store in session
        request.session['username'] = user.UserName
        request.session['user_id'] = user.UserID
        request.session['is_author'] = user.is_author
        request.session['author_completed'] = user.author_completed
        request.session['is_google_user'] = True

        # Redirect to author creation if not completed
        if user.is_author and not user.author_completed:
            return render(request, 'auth_result.html', {
                'success': True,
                'message': f'Welcome, {user.UserName}!',
                'redirect_url': '/author-create/'
            })
        else:
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

            # REMOVE EMAIL VERIFICATION CHECK
            # if not user.is_verified:
            #     return JsonResponse({
            #         'status': 'error',
            #         'message': 'Please verify your email before logging in'
            #     }, status=401)

            if not check_password(password, user.Password):
                return JsonResponse({'status': 'error', 'message': 'Invalid username or password'}, status=401)

            # Store user info in session
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
    """Email verification page"""
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

        # Update user verification status
        user.is_verified = True
        user.save(update_fields=['is_verified'])
        logger.info(f"User {user_id} successfully verified email")

        # Clean up used token
        del verification_tokens[token]
        logger.debug(f"Verification token {token[:8]}... removed from storage")

        # Store user in session
        request.session['username'] = user.UserName
        request.session['user_id'] = user.UserID
        request.session['is_author'] = user.is_author
        request.session['author_completed'] = user.author_completed
        logger.debug(f"Session updated for user {user_id}")

        # Redirect based on user type
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

            # Validation
            if not username or not password or not email:
                return JsonResponse({'status': 'error', 'message': 'All fields required'}, status=400)

            if len(username) < 3:
                return JsonResponse({'status': 'error', 'message': 'Username must be at least 3 characters'}, status=400)

            if len(password) < 6:
                return JsonResponse({'status': 'error', 'message': 'Password must be at least 6 characters'}, status=400)

            if password != confirm_password:
                return JsonResponse({'status': 'error', 'message': 'Passwords do not match'}, status=400)

            if Credentials.objects.filter(UserName=username).exists():
                return JsonResponse({'status': 'error', 'message': 'Username already exists'}, status=400)

            if Credentials.objects.filter(Email=email).exists():
                return JsonResponse({'status': 'error', 'message': 'Email already registered'}, status=400)

            # Create user
            hashed_password = make_password(password)
            user = Credentials.objects.create(
                UserName=username,
                Password=hashed_password,
                Email=email,
                is_verified=True,  # AUTO-VERIFY FOR NOW
                is_author=True,
                author_completed=False,
                Read={},
                Currently_Reading={},
                Want_To_Read={}
            )

            print(f"✅ User created: {username} (ID: {user.UserID})")

            # Store user in session immediately (skip email verification)
            request.session['username'] = username
            request.session['user_id'] = user.UserID
            request.session['is_author'] = True
            request.session['author_completed'] = False

            # Return success - user can login immediately
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
def debug_email_config(request):
    """Debug endpoint to check email configuration"""
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
    
    # Try to send a test email
    test_result = "Not attempted"
    try:
        from django.core.mail import send_mail
        send_mail(
            'BookNimbus Test Email',
            'This is a test email from BookNimbus.',
            settings.DEFAULT_FROM_EMAIL,
            [settings.DEFAULT_FROM_EMAIL],  # Send to yourself
            fail_silently=False,
        )
        test_result = "SUCCESS - Email sent"
    except Exception as e:
        test_result = f"FAILED - {str(e)}"
    
    config_info['TEST_EMAIL_RESULT'] = test_result
    
    return JsonResponse(config_info)

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

            # Check if it's a Google user
            if user.google_id:
                return JsonResponse({
                    'status': 'error',
                    'message': 'This account uses Google authentication. Please sign in with Google.'
                }, status=400)

            # Get base URL for reset links
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
    """Password reset form page"""
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
    """Logout user"""
    request.session.flush()
    return redirect('index')
