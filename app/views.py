from django.shortcuts import redirect, HttpResponse
from allauth.socialaccount.models import SocialAccount, SocialApp
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.helpers import complete_social_login
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from django.conf import settings
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def google_login(request):
    return redirect('/accounts/google/login/')

@csrf_exempt
def google_callback(request):
    if 'code' not in request.GET:
        return JsonResponse({'error': 'Authorization code not found'}, status=400)

    try:
        app = SocialApp.objects.get(provider='google')
    except SocialApp.DoesNotExist:
        return JsonResponse({'error': 'Google OAuth is not configured'}, status=500)
    except SocialApp.MultipleObjectsReturned:
        return JsonResponse({'error': 'Multiple Google OAuth configurations found'}, status=500)

    adapter = GoogleOAuth2Adapter(request)
    client = adapter.get_client(request, app)

    code = request.GET['code']

    try:
        token_dict = client.get_access_token(code)
    except Exception as e:
        return JsonResponse({'error': f'Error retrieving access token: {str(e)}'}, status=400)

    # Converting the token dictionary into an object with a 'token' attribute
    class TokenObject:
        def __init__(self, token_dict):
            self.token = token_dict['access_token']
            self.token_type = token_dict.get('token_type', 'Bearer')
            self.expires_in = token_dict.get('expires_in')

    token = TokenObject(token_dict)

    response = {
        'access_token': token.token,
        'token_type': token.token_type,
        'expires_in': token.expires_in,
    }

    login = adapter.complete_login(request, app, token, response=response)
    login.token = token.token
    complete_social_login(request, login)

    # Fetching user data
    social_account = SocialAccount.objects.get(user=request.user, provider='google')
    extra_data = social_account.extra_data

    return JsonResponse({
        'id': extra_data.get('id'),
        'access_token': token.token,
        'email': extra_data.get('email'),
        'name': extra_data.get('name'),
        'picture': extra_data.get('picture'),
    })
    
def connect_google_drive(request):
    # Set up the OAuth flow
    flow = Flow.from_client_secrets_file(
        settings.GOOGLE_DRIVE_CLIENT_SECRETS_FILE,
        scopes=['https://www.googleapis.com/auth/drive'],
        redirect_uri=request.build_absolute_uri('/auth/google/drive/callback/')
    )

    # Generate the authorization URL
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )

    # Store the state in the session for later validation
    request.session['google_drive_state'] = state

    return redirect(authorization_url)

def google_drive_callback(request):
    # Verify the state parameter
    if request.GET.get('state') != request.session.get('google_drive_state'):
        return JsonResponse({'error': 'Invalid state parameter'}, status=400)

    # Set up the OAuth flow
    flow = Flow.from_client_secrets_file(
        settings.GOOGLE_DRIVE_CLIENT_SECRETS_FILE,
        scopes=['https://www.googleapis.com/auth/drive'],
        redirect_uri=request.build_absolute_uri('/auth/google/drive/callback/')
    )

    # Fetch the access token
    flow.fetch_token(authorization_response=request.build_absolute_uri())

    # Store the credentials in the session
    credentials = flow.credentials
    request.session['google_drive_credentials'] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes,
    }

    return JsonResponse({'message': 'Google Drive connected successfully!'})

@csrf_exempt
def upload_to_google_drive(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are allowed'}, status=405)

    # Get the file from the request
    file = request.FILES.get('file')
    if not file:
        return JsonResponse({'error': 'No file provided'}, status=400)

    # Load credentials from the session
    credentials = Credentials(**request.session['google_drive_credentials'])

    # Build the Google Drive API client
    service = build('drive', 'v3', credentials=credentials)

    # Upload the file
    file_metadata = {'name': file.name}
    media = MediaFileUpload(file.temporary_file_path(), mimetype=file.content_type)
    uploaded_file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()

    return JsonResponse({'file_id': uploaded_file.get('id')})

@csrf_exempt
def download_from_google_drive(request, file_id):
    # Load credentials from the session
    credentials = Credentials(**request.session['google_drive_credentials'])

    # Build the Google Drive API client
    service = build('drive', 'v3', credentials=credentials)

    # Fetch the file metadata
    file_metadata = service.files().get(fileId=file_id, fields='name').execute()

    # Download the file
    request = service.files().get_media(fileId=file_id)
    response = request.execute()

    # Return the file as a downloadable response
    response = HttpResponse(response, content_type='application/octet-stream')
    response['Content-Disposition'] = f'attachment; filename="{file_metadata["name"]}"'
    return response