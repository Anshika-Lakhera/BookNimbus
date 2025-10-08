import json
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login


def index(request):
    """Render the main login/signup page"""
    return render(request, 'index.html')


@csrf_exempt
def login_view(request):
    """Handle login requests"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            username = data.get('username')
            password = data.get('password')

            # Authenticate user
            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)
                print(f"\n✓ LOGIN SUCCESSFUL")
                print(f"Username: {username}")
                print(f"User ID: {user.id}")
                print(f"Email: {user.email if user.email else 'Not provided'}")
                print("-" * 40)

                return JsonResponse({
                    'status': 'success',
                    'message': f'Welcome back, {username}!'
                })
            else:
                print(f"\n✗ LOGIN FAILED")
                print(f"Username: {username}")
                print(f"Reason: Invalid credentials")
                print("-" * 40)

                return JsonResponse({
                    'status': 'error',
                    'message': 'Invalid username or password'
                }, status=401)

        except Exception as e:
            print(f"\n✗ LOGIN ERROR: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': 'An error occurred during login'
            }, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)


@csrf_exempt
def signup_view(request):
    """Handle signup requests"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            username = data.get('username')
            password = data.get('password')
            confirm_password = data.get('confirm_password')

            # Validate passwords match
            if password != confirm_password:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Passwords do not match'
                }, status=400)

            # Check if user already exists
            if User.objects.filter(username=username).exists():
                print(f"\n✗ SIGNUP FAILED")
                print(f"Username: {username}")
                print(f"Reason: Username already exists")
                print("-" * 40)

                return JsonResponse({
                    'status': 'error',
                    'message': 'Username already exists'
                }, status=400)

            # Create new user
            user = User.objects.create_user(
                username=username,
                password=password
            )

            # Print user details
            print(f"\n✓ SIGNUP SUCCESSFUL")
            print(f"Username: {username}")
            print(f"User ID: {user.id}")
            print(f"Date Joined: {user.date_joined}")
            print(f"Password Length: {len(password)} characters")
            print(f"Is Active: {user.is_active}")
            print(f"Is Staff: {user.is_staff}")
            print(f"Is Superuser: {user.is_superuser}")
            print("-" * 40)

            # Auto-login after signup
            login(request, user)

            return JsonResponse({
                'status': 'success',
                'message': f'Account created successfully! Welcome, {username}!'
            })

        except Exception as e:
            print(f"\n✗ SIGNUP ERROR: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': 'An error occurred during signup'
            }, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)