import json
import requests
import uuid
import logging
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
from django.db import connection

# Configure logging
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
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://arwnfwtjpjhegtgdrpmi.supabase.co')
SUPABASE_ANON_KEY = os.environ.get('SUPABASE_ANON_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFyd25md3RqcGpoZWd0Z2RycG1pIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjAwMTM5MjAsImV4cCI6MjA3NTU4OTkyMH0.JUf22-Rt6LLnGjWULe4VZYNg_tH5aVlgclxx7JKL3yA')
SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFyd25md3RqcGpoZWd0Z2RycG1pIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MDAxMzkyMCwiZXhwIjoyMDc1NTg5OTIwfQ.FPYRFHub7dGv7zOuHitIbpcUYiVRd39WWuaK9vvD7pc')

def index(request):
    """Home page view"""
    logger.info(f"Home page accessed - IP: {get_client_ip(request)}")
    return render(request, 'index.html')

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
    client_ip = get_client_ip(request)

    logger.info(f"Shelves page accessed - Username: {username}, UserID: {user_id}, IP: {client_ip}")

    if not username:
        logger.warning(f"Unauthorized shelves access - IP: {client_ip}")
        return redirect('index')

    # Ensure user_id is properly set
    if not user_id:
        try:
            user = Credentials.objects.get(UserName=username)
            user_id = user.UserID
            request.session['user_id'] = user_id
            request.session['is_author'] = user.is_author
            request.session['author_completed'] = user.author_completed
            logger.debug(f"Session updated with user data - UserID: {user_id}")
        except Credentials.DoesNotExist:
            logger.error(f"User not found in shelves - Username: {username}, IP: {client_ip}")
            return redirect('index')

    # Check if user needs author onboarding
    user_obj = Credentials.objects.get(UserID=user_id)
    if user_obj.is_author and not user_obj.author_completed:
        logger.info(f"Redirecting to author creation - UserID: {user_id}")
        return redirect('author_create')

    logger.debug(f"Rendering shelves for user_id: {user_id}")

    return render(request, 'shelves.html', {
        'username': username,
        'user_id': user_id,
        'is_author': request.session.get('is_author', False),
        'author_completed': request.session.get('author_completed', False)
    })

def author_create(request):
    """Author profile creation page - sets is_author to True"""
    username = request.session.get('username')
    user_id = request.session.get('user_id')
    client_ip = get_client_ip(request)

    logger.info(f"Author creation page accessed - Username: {username}, UserID: {user_id}, IP: {client_ip}")

    if not username:
        return redirect('index')

    # Get user object
    try:
        user = Credentials.objects.get(UserID=user_id)

        # If user is already completed author onboarding, redirect to home
        if user.author_completed:
            logger.info(f"User already completed author onboarding - UserID: {user_id}")
            return redirect('home')

    except Credentials.DoesNotExist:
        logger.error(f"User not found in author_create - UserID: {user_id}, IP: {client_ip}")
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

            logger.info(f"Author profile created successfully - UserID: {user_id}, Username: {username}")

            return JsonResponse({
                'status': 'success',
                'message': 'Author profile created successfully!',
                'redirect': '/home/'
            })
        except Exception as e:
            logger.error(f"Error creating author profile - UserID: {user_id}, Error: {str(e)}", exc_info=True)
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
    client_ip = get_client_ip(request)

    logger.info(f"Author books page accessed - Author: {author_name}, Username: {username}, IP: {client_ip}")

    if not username:
        return redirect('index')

    # Get books by author
    books = Books.get_books_by_author(author_name)
    books_data = [book.to_dict() for book in books]

    logger.debug(f"Found {len(books_data)} books for author: {author_name}")

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
    author_filter = request.GET.get('author', None)
    client_ip = get_client_ip(request)

    logger.info(f"Books API called - Author filter: {author_filter}, IP: {client_ip}")

    try:
        if author_filter:
            # Get books by specific author
            books_queryset = Books.get_books_by_author(author_filter)
            logger.debug(f"Filtering books by author: {author_filter}")
        else:
            # Get all books
            books_queryset = Books.get_all_books()
            logger.debug("Fetching all books")

        # Convert to list of dictionaries
        books_data = [book.to_dict() for book in books_queryset]

        if books_data:
            logger.info(f"Successfully fetched {len(books_data)} books")
            return JsonResponse({
                'success': True,
                'books': books_data
            })
        else:
            logger.info("No books found")
            return JsonResponse({
                'success': True,
                'books': [],
                'message': 'No books found'
            })

    except Exception as e:
        logger.error(f"Error fetching books - Error: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

def epub_reader(request):
    """EPUB Reader page"""
    client_ip = get_client_ip(request)
    logger.info(f"EPUB reader accessed - IP: {client_ip}")
    return render(request, 'epub_reader.html')

def home(request):
    """Home screen after login"""
    username = request.session.get('username')
    user_id = request.session.get('user_id')
    client_ip = get_client_ip(request)

    logger.info(f"Home page accessed - Username: {username}, UserID: {user_id}, IP: {client_ip}")

    if not username:
        logger.warning(f"Unauthorized home access - IP: {client_ip}")
        return redirect('index')

    # If user_id is not in session, try to get it from the database
    if not user_id:
        try:
            user = Credentials.objects.get(UserName=username)
            user_id = user.UserID
            request.session['user_id'] = user_id
            request.session['is_author'] = user.is_author
            request.session['author_completed'] = user.author_completed
            logger.debug(f"Session updated with user data - UserID: {user_id}")
        except Credentials.DoesNotExist:
            logger.error(f"User not found in home - Username: {username}, IP: {client_ip}")
            return redirect('index')

    # Check if user needs author onboarding
    user_obj = Credentials.objects.get(UserID=user_id)
    if user_obj.is_author and not user_obj.author_completed:
        logger.info(f"Redirecting to author creation from home - UserID: {user_id}")
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
    client_ip = get_client_ip(request)
    
    try:
        data = json.loads(request.body)
        user_id = data.get('user_id')
        book_id = data.get('book_id')
        status = data.get('status')
        book_data = data.get('book_data', {})

        logger.info(f"Updating reading status - UserID: {user_id}, BookID: {book_id}, Status: {status}, IP: {client_ip}")

        if not all([user_id, book_id, status]):
            logger.warning(f"Missing required fields in reading status update - UserID: {user_id}, BookID: {book_id}, IP: {client_ip}")
            return JsonResponse({'error': 'Missing required fields'}, status=400)

        try:
            user = Credentials.objects.get(UserID=user_id)
            user.update_reading_status(book_id, book_data, status)

            logger.info(f"Reading status updated successfully - UserID: {user_id}, BookID: {book_id}, Status: {status}")

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
            logger.error(f"User not found for reading status update - UserID: {user_id}, IP: {client_ip}")
            return JsonResponse({'error': 'User not found'}, status=404)

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in reading status update - IP: {client_ip}, Error: {str(e)}")
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Unexpected error in reading status update - IP: {client_ip}, Error: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

@require_http_methods(["GET"])
def get_reading_status(request, user_id):
    """Get all reading status for a user"""
    client_ip = get_client_ip(request)
    
    logger.info(f"Getting reading status - UserID: {user_id}, IP: {client_ip}")

    try:
        user = Credentials.objects.get(UserID=user_id)
        logger.debug(f"User found: {user.UserName}")

        # Initialize None fields to empty dict
        if user.Read is None:
            user.Read = {}
        if user.Currently_Reading is None:
            user.Currently_Reading = {}
        if user.Want_To_Read is None:
            user.Want_To_Read = {}

        reading_status = user.get_reading_status()
        logger.debug(f"Reading status retrieved - UserID: {user_id}")

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
        logger.error(f"User not found for reading status - UserID: {user_id}, IP: {client_ip}")
        return JsonResponse({'error': 'User not found'}, status=404)
    except Exception as e:
        logger.error(f"Error in get_reading_status - UserID: {user_id}, Error: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

@require_http_methods(["GET"])
def get_user_stats(request, user_id):
    """Get user reading statistics"""
    client_ip = get_client_ip(request)
    
    logger.info(f"Getting user stats - UserID: {user_id}, IP: {client_ip}")

    try:
        user = Credentials.objects.get(UserID=user_id)

        # Initialize None fields to empty dict
        if user.Read is None:
            user.Read = {}
        if user.Currently_Reading is None:
            user.Currently_Reading = {}
        if user.Want_To_Read is None:
            user.Want_To_Read = {}

        stats = {
            'want_to_read': len(user.Want_To_Read),
            'currently_reading': len(user.Currently_Reading),
            'read': len(user.Read)
        }

        logger.debug(f"User stats retrieved - UserID: {user_id}, Stats: {stats}")

        return JsonResponse({
            'success': True,
            'stats': stats
        })

    except Credentials.DoesNotExist:
        logger.error(f"User not found for stats - UserID: {user_id}, IP: {client_ip}")
        return JsonResponse({'error': 'User not found'}, status=404)
    except Exception as e:
        logger.error(f"Error in get_user_stats - UserID: {user_id}, Error: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def create_post(request):
    """Create new book post"""
    username = request.session.get('username')
    user_id = request.session.get('user_id')
    client_ip = get_client_ip(request)

    logger.info(f"Create post page accessed - Username: {username}, UserID: {user_id}, IP: {client_ip}")

    if not username or not user_id:
        logger.warning(f"Unauthorized create post access - IP: {client_ip}")
        return JsonResponse({'status': 'error', 'message': 'Not authenticated'}, status=401)

    # Check if user is author
    try:
        user = Credentials.objects.get(UserID=user_id)
        if not user.is_author:
            logger.warning(f"Non-author attempting to create post - UserID: {user_id}, IP: {client_ip}")
            return JsonResponse({'status': 'error', 'message': 'Not an author'}, status=403)
    except Credentials.DoesNotExist:
        logger.error(f"User not found for create post - UserID: {user_id}, IP: {client_ip}")
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

            logger.info(f"Creating book post - Title: {title}, Author: {author}, UserID: {user_id}")

            # Validate required fields
            if not all([title, author, genre, year, cover_file, epub_file]):
                logger.warning(f"Missing required fields in create post - UserID: {user_id}, Title: {title}")
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
                logger.error(f"Failed to upload cover image - UserID: {user_id}, Title: {title}")
                return JsonResponse({
                    'status': 'error',
                    'message': 'Failed to upload cover image'
                }, status=500)

            # Upload EPUB to Supabase
            epub_url = upload_to_supabase(epub_file, 'Books', epub_filename)
            if not epub_url:
                logger.error(f"Failed to upload EPUB file - UserID: {user_id}, Title: {title}")
                return JsonResponse({
                    'status': 'error',
                    'message': 'Failed to upload EPUB file'
                }, status=500)

            # Get next book ID from sequence
            next_book_id = get_next_book_id()
            logger.debug(f"Next book ID from sequence: {next_book_id}")

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

            logger.info(f"Book created successfully - BookID: {book.bookid}, Title: {title}, UserID: {user_id}")

            return JsonResponse({
                'status': 'success',
                'message': 'Book published successfully!',
                'book_id': book.bookid
            })

        except Exception as e:
            logger.error(f"Error creating post - UserID: {user_id}, Error: {str(e)}", exc_info=True)
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

        logger.debug(f"Uploading to Supabase - URL: {upload_url}, File size: {len(file_data)} bytes, Bucket: {bucket_name}")

        # Upload file using POST
        response = requests.post(
            upload_url,
            headers=headers,
            data=file_data
        )

        logger.debug(f"Supabase upload response - Status: {response.status_code}")

        if response.status_code == 200:
            # Return public URL
            public_url = f"{SUPABASE_URL}/storage/v1/object/public/{bucket_name}/{filename}"
            logger.info(f"Upload successful - URL: {public_url}")
            return public_url
        else:
            logger.error(f"Supabase upload error - Status: {response.status_code}, Response: {response.text}")
            return None

    except Exception as e:
        logger.error(f"Error uploading to Supabase - Error: {str(e)}", exc_info=True)
        return None

@csrf_exempt
def google_auth_init(request):
    """Start Google OAuth flow"""
    client_ip = get_client_ip(request)
    logger.info(f"Google OAuth initiation - IP: {client_ip}")
    
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
        logger.debug(f"Google OAuth URL generated - IP: {client_ip}")
        return JsonResponse({'auth_url': auth_url})

    logger.warning(f"Invalid request method for Google OAuth - Method: {request.method}, IP: {client_ip}")
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})

@csrf_exempt
def google_callback(request):
    """Handle Google OAuth callback"""
    code = request.GET.get('code')
    client_ip = get_client_ip(request)

    logger.info(f"Google OAuth callback - Code: {code}, IP: {client_ip}")

    if not code:
        logger.warning(f"No authorization code in Google callback - IP: {client_ip}")
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
            logger.error(f"Token exchange failed - Error: {token_json['error']}, IP: {client_ip}")
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
            logger.error(f"Failed to get user info - Error: {userinfo['error']}, IP: {client_ip}")
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

        logger.info(f"Google user info - GoogleID: {google_id}, Email: {email}, Name: {name}")

        # Check if user exists by google_id
        user = Credentials.objects.filter(google_id=google_id).first()

        if not user:
            # Check if user exists by email (for existing users linking Google)
            user = Credentials.objects.filter(Email=email).first()

            if user:
                # Link existing account with Google
                user.google_id = google_id
                user.save(update_fields=['google_id'])
                logger.info(f"Linked existing account with Google - UserID: {user.UserID}, Email: {email}")
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
                logger.info(f"Created new user via Google - UserID: {user.UserID}, Username: {username}, Email: {email}")

        # Store in session
        request.session['username'] = user.UserName
        request.session['user_id'] = user.UserID
        request.session['is_author'] = user.is_author
        request.session['author_completed'] = user.author_completed
        request.session['is_google_user'] = True

        logger.info(f"Google authentication successful - UserID: {user.UserID}, Username: {user.UserName}")

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
        logger.error(f"Google OAuth error - Error: {str(e)}", exc_info=True)
        return render(request, 'auth_result.html', {
            'success': False,
            'message': 'Authentication failed. Please try again.'
        })

@csrf_exempt
def login_view(request):
    """Enhanced login view with detailed logging"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            username = data.get('username', '').strip()
            password = data.get('password', '')
            client_ip = get_client_ip(request)

            logger.info(f"Login attempt - Username: {username}, IP: {client_ip}")

            if not username or not password:
                logger.warning(f"Missing credentials - Username: {username}, IP: {client_ip}")
                return JsonResponse({
                    'status': 'error', 
                    'message': 'Username and password required'
                }, status=400)

            # Log the attempt (without password)
            logger.debug(f"Looking up user: {username}")

            user = Credentials.objects.filter(UserName=username).first()

            if not user:
                logger.warning(f"User not found - Username: {username}, IP: {client_ip}")
                return JsonResponse({
                    'status': 'error', 
                    'message': 'Invalid username or password'
                }, status=401)

            # Check if this is a Google user trying to use password
            if user.google_id and not user.Password:
                logger.warning(f"Google user attempted password login - Username: {username}, IP: {client_ip}")
                return JsonResponse({
                    'status': 'error',
                    'message': 'This account uses Google authentication. Please sign in with Google.'
                }, status=401)

            # Verify password
            if not check_password(password, user.Password):
                logger.warning(f"Invalid password - Username: {username}, IP: {client_ip}")
                return JsonResponse({
                    'status': 'error', 
                    'message': 'Invalid username or password'
                }, status=401)

            if not user.is_verified:
                logger.warning(f"Unverified email attempt - Username: {username}, IP: {client_ip}")
                return JsonResponse({
                    'status': 'error',
                    'message': 'Please verify your email before logging in'
                }, status=401)

            # Successful login
            logger.info(f"Successful login - UserID: {user.UserID}, Username: {username}, IP: {client_ip}")

            # Store user info in session
            request.session['username'] = username
            request.session['user_id'] = user.UserID
            request.session['is_author'] = user.is_author
            request.session['author_completed'] = user.author_completed
            request.session['is_google_user'] = False

            # DEBUG: Check author status
            logger.debug(f"User {username}: is_author={user.is_author}, author_completed={user.author_completed}")

            # Redirect to author creation if user is marked as author but hasn't completed onboarding
            if user.is_author and not user.author_completed:
                logger.info(f"Redirecting to author creation - Username: {username}")
                return JsonResponse({
                    'status': 'success',
                    'message': f'Welcome back, {username}!',
                    'redirect': '/author-create/',
                    'is_author': user.is_author
                })
            else:
                return JsonResponse({
                    'status': 'success',
                    'message': f'Welcome back, {username}!',
                    'redirect': '/home/',
                    'is_author': user.is_author
                })

        except json.JSONDecodeError as e:
            client_ip = get_client_ip(request)
            logger.error(f"JSON decode error in login - IP: {client_ip}, Error: {str(e)}")
            return JsonResponse({
                'status': 'error', 
                'message': 'Invalid request format'
            }, status=400)
            
        except Exception as e:
            client_ip = get_client_ip(request)
            logger.error(f"Unexpected login error - IP: {client_ip}, Error: {str(e)}", exc_info=True)
            return JsonResponse({
                'status': 'error', 
                'message': 'Error during login. Please try again.'
            }, status=500)

    logger.warning(f"Invalid request method for login: {request.method}")
    return JsonResponse({
        'status': 'error', 
        'message': 'Invalid request method'
    }, status=405)

@csrf_exempt
def signup_view(request):
    """Enhanced signup view with detailed logging"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            username = data.get('username', '').strip()
            email = data.get('email', '').strip().lower()
            password = data.get('password', '')
            confirm_password = data.get('confirm_password', '')
            client_ip = get_client_ip(request)

            logger.info(f"Signup attempt - Username: {username}, Email: {email}, IP: {client_ip}")

            # Validation
            if not username or not password or not email:
                logger.warning(f"Missing signup fields - Username: {username}, Email: {email}, IP: {client_ip}")
                return JsonResponse({
                    'status': 'error', 
                    'message': 'All fields required'
                }, status=400)

            if len(username) < 3:
                logger.warning(f"Username too short - Username: {username}, IP: {client_ip}")
                return JsonResponse({
                    'status': 'error', 
                    'message': 'Username must be at least 3 characters'
                }, status=400)

            if len(password) < 6:
                logger.warning(f"Password too short - Username: {username}, IP: {client_ip}")
                return JsonResponse({
                    'status': 'error', 
                    'message': 'Password must be at least 6 characters'
                }, status=400)

            if password != confirm_password:
                logger.warning(f"Password mismatch - Username: {username}, IP: {client_ip}")
                return JsonResponse({
                    'status': 'error', 
                    'message': 'Passwords do not match'
                }, status=400)

            # Check for existing username
            if Credentials.objects.filter(UserName=username).exists():
                logger.warning(f"Username already exists - Username: {username}, IP: {client_ip}")
                return JsonResponse({
                    'status': 'error', 
                    'message': 'Username already exists'
                }, status=400)

            # Check for existing email
            if Credentials.objects.filter(Email=email).exists():
                logger.warning(f"Email already registered - Email: {email}, IP: {client_ip}")
                return JsonResponse({
                    'status': 'error', 
                    'message': 'Email already registered'
                }, status=400)

            # Create user
            hashed_password = make_password(password)
            user = Credentials.objects.create(
                UserName=username,
                Password=hashed_password,
                Email=email,
                is_verified=False,
                is_author=True,  # NEW: Set all new users as authors by default
                author_completed=False,  # They need to complete onboarding
                Read={},
                Currently_Reading={},
                Want_To_Read={}
            )

            logger.info(f"User created successfully - UserID: {user.UserID}, Username: {username}, Email: {email}")

            # Get base URL for verification links
            base_url = 'book-nimbus.onrender.com'

            # Verification token
            token = get_random_string(32)
            verification_tokens[token] = user.UserID

            verification_link = f"{base_url}/verify-email/?token={token}"
            
            # Send verification email
            try:
                send_mail(
                    'Verify your BookNimbus account',
                    f'Welcome to BookNimbus!\n\nClick the link below to verify your email:\n{verification_link}\n\nThis link will expire in 24 hours.',
                    'noreply@booknimbus.com',
                    [email],
                    fail_silently=False,
                )
                logger.info(f"Verification email sent - UserID: {user.UserID}, Email: {email}")
            except Exception as e:
                logger.error(f"Failed to send verification email - UserID: {user.UserID}, Error: {str(e)}")

            return JsonResponse({
                'status': 'success',
                'message': 'Account created! Please check your email to verify your account.'
            })

        except json.JSONDecodeError as e:
            client_ip = get_client_ip(request)
            logger.error(f"JSON decode error in signup - IP: {client_ip}, Error: {str(e)}")
            return JsonResponse({
                'status': 'error', 
                'message': 'Invalid request format'
            }, status=400)
            
        except Exception as e:
            client_ip = get_client_ip(request)
            logger.error(f"Unexpected signup error - IP: {client_ip}, Error: {str(e)}", exc_info=True)
            return JsonResponse({
                'status': 'error', 
                'message': 'Error during signup. Please try again.'
            }, status=500)

    logger.warning(f"Invalid request method for signup: {request.method}")
    return JsonResponse({
        'status': 'error', 
        'message': 'Invalid request method'
    }, status=405)

def verify_email(request):
    """Email verification page with logging"""
    token = request.GET.get('token')
    client_ip = get_client_ip(request)
    
    logger.info(f"Email verification attempt - Token: {token}, IP: {client_ip}")

    if not token:
        logger.warning(f"No verification token provided - IP: {client_ip}")
        return render(request, 'verify_result.html', {
            'success': False,
            'message': 'No verification token provided'
        })

    user_id = verification_tokens.get(token)
    if user_id:
        user = Credentials.objects.filter(UserID=user_id).first()
        if user:
            user.is_verified = True
            user.save(update_fields=['is_verified'])
            del verification_tokens[token]

            logger.info(f"Email verified successfully - UserID: {user.UserID}, Username: {user.UserName}")

            # Store user in session and redirect to author creation
            request.session['username'] = user.UserName
            request.session['user_id'] = user.UserID
            request.session['is_author'] = user.is_author
            request.session['author_completed'] = user.author_completed

            # If user is author but hasn't completed onboarding, redirect to author creation
            if user.is_author and not user.author_completed:
                logger.info(f"Redirecting to author creation after verification - UserID: {user.UserID}")
                return render(request, 'verify_result.html', {
                    'success': True,
                    'message': 'Email verified successfully! Setting up your author profile...',
                    'redirect_url': '/author-create/'
                })
            else:
                return render(request, 'verify_result.html', {
                    'success': True,
                    'message': 'Email verified successfully!',
                    'redirect_url': '/home/'
                })

    logger.warning(f"Invalid verification token - Token: {token}, IP: {client_ip}")
    return render(request, 'verify_result.html', {
        'success': False,
        'message': 'Invalid or expired verification token'
    })

@csrf_exempt
def forgot_password(request):
    """Forgot password with enhanced logging"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            email = data.get('email', '').strip().lower()
            client_ip = get_client_ip(request)

            logger.info(f"Password reset request - Email: {email}, IP: {client_ip}")

            if not email:
                logger.warning(f"Missing email in password reset - IP: {client_ip}")
                return JsonResponse({
                    'status': 'error', 
                    'message': 'Email required'
                }, status=400)

            user = Credentials.objects.filter(Email=email).first()
            if not user:
                logger.warning(f"Password reset for non-existent email - Email: {email}, IP: {client_ip}")
                return JsonResponse({
                    'status': 'error', 
                    'message': 'No account found with this email'
                }, status=404)

            # Check if it's a Google user
            if user.google_id:
                logger.warning(f"Password reset attempt for Google user - Email: {email}, IP: {client_ip}")
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
                logger.info(f"Password reset email sent - UserID: {user.UserID}, Email: {email}")
            except Exception as e:
                logger.error(f"Failed to send password reset email - UserID: {user.UserID}, Error: {str(e)}")
                return JsonResponse({
                    'status': 'error',
                    'message': 'Error sending reset email. Please try again.'
                }, status=500)

            return JsonResponse({
                'status': 'success',
                'message': 'Password reset link sent to your email'
            })

        except json.JSONDecodeError as e:
            client_ip = get_client_ip(request)
            logger.error(f"JSON decode error in forgot password - IP: {client_ip}, Error: {str(e)}")
            return JsonResponse({
                'status': 'error', 
                'message': 'Invalid request format'
            }, status=400)
            
        except Exception as e:
            client_ip = get_client_ip(request)
            logger.error(f"Unexpected error in forgot password - IP: {client_ip}, Error: {str(e)}", exc_info=True)
            return JsonResponse({
                'status': 'error', 
                'message': 'Error sending reset email'
            }, status=500)

    logger.warning(f"Invalid request method for forgot password: {request.method}")
    return JsonResponse({
        'status': 'error', 
        'message': 'Invalid request method'
    }, status=405)

@csrf_exempt
def reset_password(request):
    """Reset password with enhanced logging"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            token = data.get('token')
            new_password = data.get('password')
            confirm_password = data.get('confirm_password')
            client_ip = get_client_ip(request)

            logger.info(f"Password reset attempt - Token: {token}, IP: {client_ip}")

            if not token or not new_password:
                logger.warning(f"Missing token or password in reset - IP: {client_ip}")
                return JsonResponse({
                    'status': 'error', 
                    'message': 'Token and password required'
                }, status=400)

            if len(new_password) < 6:
                logger.warning(f"Password too short in reset - IP: {client_ip}")
                return JsonResponse({
                    'status': 'error', 
                    'message': 'Password must be at least 6 characters'
                }, status=400)

            if new_password != confirm_password:
                logger.warning(f"Password mismatch in reset - IP: {client_ip}")
                return JsonResponse({
                    'status': 'error', 
                    'message': 'Passwords do not match'
                }, status=400)

            user_id = password_reset_tokens.get(token)
            if not user_id:
                logger.warning(f"Invalid reset token - Token: {token}, IP: {client_ip}")
                return JsonResponse({
                    'status': 'error', 
                    'message': 'Invalid or expired token'
                }, status=400)

            user = Credentials.objects.filter(UserID=user_id).first()
            if user:
                user.Password = make_password(new_password)
                user.save(update_fields=['Password'])
                del password_reset_tokens[token]

                logger.info(f"Password reset successful - UserID: {user.UserID}, Username: {user.UserName}")

                return JsonResponse({
                    'status': 'success',
                    'message': 'Password updated successfully! You can now login.'
                })

            logger.warning(f"User not found for reset token - Token: {token}, IP: {client_ip}")
            return JsonResponse({
                'status': 'error', 
                'message': 'User not found'
            }, status=404)

        except json.JSONDecodeError as e:
            client_ip = get_client_ip(request)
            logger.error(f"JSON decode error in reset password - IP: {client_ip}, Error: {str(e)}")
            return JsonResponse({
                'status': 'error', 
                'message': 'Invalid request format'
            }, status=400)
            
        except Exception as e:
            client_ip = get_client_ip(request)
            logger.error(f"Unexpected error in reset password - IP: {client_ip}, Error: {str(e)}", exc_info=True)
            return JsonResponse({
                'status': 'error', 
                'message': 'Error resetting password'
            }, status=500)

    logger.warning(f"Invalid request method for reset password: {request.method}")
    return JsonResponse({
        'status': 'error', 
        'message': 'Invalid request method'
    }, status=405)


def reset_password_page(request):
    """Password reset form page"""
    token = request.GET.get('token')
    client_ip = get_client_ip(request)
    
    logger.info(f"Password reset page accessed - Token: {token}, IP: {client_ip}")

    if not token or token not in password_reset_tokens:
        logger.warning(f"Invalid or missing reset token - Token: {token}, IP: {client_ip}")
        return render(request, 'reset_password.html', {
            'valid_token': False,
            'message': 'Invalid or expired reset link'
        })

    logger.info(f"Valid reset token - Token: {token}, IP: {client_ip}")
    return render(request, 'reset_password.html', {
        'valid_token': True,
        'token': token
    })

def logout_view(request):
    """Logout user"""
    username = request.session.get('username')
    user_id = request.session.get('user_id')
    client_ip = get_client_ip(request)
    
    logger.info(f"User logout - Username: {username}, UserID: {user_id}, IP: {client_ip}")
    
    request.session.flush()
    return redirect('index')

def get_client_ip(request):
    """Get client IP address for logging"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
