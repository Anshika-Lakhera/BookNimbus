import json
import requests
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.hashers import make_password, check_password
from django.core.mail import send_mail
from django.utils.crypto import get_random_string
from django.conf import settings
from .models import Credentials

# In-memory tokens (for demo)
verification_tokens = {}
password_reset_tokens = {}

# Google OAuth2 Configuration - REPLACE WITH YOUR ACTUAL CREDENTIALS
GOOGLE_CLIENT_ID = '1098327710097-5mqs9s1linj3rqck41phtl7ibh18u5ra.apps.googleusercontent.com'
GOOGLE_CLIENT_SECRET = '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'
GOOGLE_REDIRECT_URI = 'http://127.0.0.1:8000/google-callback/'


def index(request):
    return render(request, 'index.html')


def home(request):
    """Home screen after login"""
    username = request.session.get('username')
    if not username:
        return redirect('index')
    return render(request, 'home.html', {'username': username})


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
                    is_verified=True
                )

        # Store in session
        request.session['username'] = user.UserName
        request.session['user_id'] = user.UserID
        request.session['is_google_user'] = True

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
def signup_view(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            username = data.get('username')
            email = data.get('email')
            password = data.get('password')
            confirm_password = data.get('confirm_password')

            # Validation
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
                is_verified=False
            )

            # Verification token
            token = get_random_string(32)
            verification_tokens[token] = user.UserID

            verification_link = f"http://127.0.0.1:8000/verify-email/?token={token}"
            send_mail(
                'Verify your BookNimbus account',
                f'Welcome to BookNimbus!\n\nClick the link below to verify your email:\n{verification_link}\n\nThis link will expire in 24 hours.',
                'noreply@booknimbus.com',
                [email],
                fail_silently=False,
            )

            return JsonResponse({
                'status': 'success',
                'message': 'Account created! Please check your email to verify your account.'
            })

        except Exception as e:
            print(f"✗ SIGNUP ERROR: {e}")
            return JsonResponse({'status': 'error', 'message': 'Error during signup'}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)


def verify_email(request):
    """Email verification page"""
    token = request.GET.get('token')
    if not token:
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
            return render(request, 'verify_result.html', {
                'success': True,
                'message': 'Email verified successfully! You can now login.'
            })

    return render(request, 'verify_result.html', {
        'success': False,
        'message': 'Invalid or expired verification token'
    })


@csrf_exempt
def login_view(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            username = data.get('username')
            password = data.get('password')

            if not username or not password:
                return JsonResponse({'status': 'error', 'message': 'Username and password required'}, status=400)

            user = Credentials.objects.filter(UserName=username).first()

            if not user:
                return JsonResponse({'status': 'error', 'message': 'Invalid username or password'}, status=401)

            # Check if this is a Google user trying to use password
            if user.google_id and not user.Password:
                return JsonResponse({
                    'status': 'error',
                    'message': 'This account uses Google authentication. Please sign in with Google.'
                }, status=401)

            if not check_password(password, user.Password):
                return JsonResponse({'status': 'error', 'message': 'Invalid username or password'}, status=401)

            if not user.is_verified:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Please verify your email before logging in'
                }, status=401)

            # Store username in session
            request.session['username'] = username
            request.session['user_id'] = user.UserID
            request.session['is_google_user'] = False

            return JsonResponse({
                'status': 'success',
                'message': f'Welcome back, {username}!',
                'redirect': '/home/'
            })

        except Exception as e:
            print(f"✗ LOGIN ERROR: {e}")
            return JsonResponse({'status': 'error', 'message': 'Error during login'}, status=500)

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

            # Check if it's a Google user
            if user.google_id:
                return JsonResponse({
                    'status': 'error',
                    'message': 'This account uses Google authentication. Please sign in with Google.'
                }, status=400)

            token = get_random_string(32)
            password_reset_tokens[token] = user.UserID
            reset_link = f"http://127.0.0.1:8000/reset-password-page/?token={token}"

            send_mail(
                'Reset your BookNimbus password',
                f'Hi {user.UserName},\n\nYou requested to reset your password.\n\nClick the link below to reset:\n{reset_link}\n\nThis link will expire in 1 hour.\n\nIf you didn\'t request this, please ignore this email.',
                'noreply@booknimbus.com',
                [email],
                fail_silently=False,
            )

            return JsonResponse({
                'status': 'success',
                'message': 'Password reset link sent to your email'
            })

        except Exception as e:
            print(f"✗ FORGOT PASSWORD ERROR: {e}")
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