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
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
import io

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
        'code': code,
        'email': extra_data.get('email'),
        'name': extra_data.get('name'),
        'picture': extra_data.get('picture'),
    })
    
def connect_google_drive(request):
    # Set up the OAuth flow
    flow = Flow.from_client_secrets_file(
        settings.GOOGLE_DRIVE_CLIENT_SECRETS_FILE,
        scopes=[
            'https://www.googleapis.com/auth/drive',
            'openid',
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/userinfo.profile'
        ],
        redirect_uri=request.build_absolute_uri('/auth/google/drive/callback/')
    )

    # Generate the authorization URL with offline access and forced consent
    authorization_url, state = flow.authorization_url(
        access_type='offline',   # Ensures we get a refresh token
        include_granted_scopes='true',
        prompt='consent'   # Forces Google to show consent screen every time
    )

    # Store the state in the session for later validation
    request.session['google_drive_state'] = state
    # print(f"---------------- Authorization url: {authorization_url} -------------------")
    return redirect(authorization_url)

def google_drive_callback(request):
    # Verify the state parameter
    if request.GET.get('state') != request.session.get('google_drive_state'):
        return JsonResponse({'error': 'Invalid state parameter'}, status=400)

    # Set up the OAuth flow
    flow = Flow.from_client_secrets_file(
        settings.GOOGLE_DRIVE_CLIENT_SECRETS_FILE,
        scopes=[
            'https://www.googleapis.com/auth/drive',
            'openid',
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/userinfo.profile'
        ],
        redirect_uri=request.build_absolute_uri('/auth/google/drive/callback/')
    )

    # Fetch the access token
    flow.fetch_token(authorization_response=request.build_absolute_uri())

    # Store the credentials in the session
    credentials = flow.credentials
    request.session['google_drive_credentials'] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,  # May be None if already authorized
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes,
    }
    # print(f"------------- Drive credentials = {request.session['google_drive_credentials']} ---------------")

    # If refresh_token is missing, warn the user
    if not credentials.refresh_token:
        return JsonResponse({
            'message': 'Google Drive connected, but no refresh token received! '
                       'Try disconnecting and reconnecting your Google account.'
        })

    return JsonResponse({'message': 'Google Drive connected successfully!',
                         'credentials': credentials})

@csrf_exempt
def upload_to_google_drive(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are allowed'}, status=405)

    # Get the file from the request
    file = request.FILES.get('file')
    if not file:
        return JsonResponse({'error': 'No file provided'}, status=400)

    # Load credentials from the session
    credentials_dict = request.session.get('google_drive_credentials')
    if not credentials_dict:
        return JsonResponse({'error': 'Google Drive not authenticated'}, status=401)

    credentials = Credentials(**credentials_dict)

    # Build the Google Drive API client
    service = build('drive', 'v3', credentials=credentials)

    # Upload the file
    file_metadata = {'name': file.name}
    media = MediaIoBaseUpload(io.BytesIO(file.read()), mimetype=file.content_type, resumable=True)

    uploaded_file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()

    return JsonResponse({'message': 'File uploaded successfully', 'file_id': uploaded_file.get('id')})

@csrf_exempt
def download_from_google_drive(request, file_id):
    # Load credentials from the session
    credentials_dict = request.session.get('google_drive_credentials')
    if not credentials_dict:
        return JsonResponse({'error': 'Google Drive not authenticated'}, status=401)

    credentials = Credentials(**credentials_dict)

    # Build the Google Drive API client
    service = build('drive', 'v3', credentials=credentials)

    try:
        # Fetch file metadata
        file_metadata = service.files().get(fileId=file_id, fields='name').execute()
        file_name = file_metadata['name']

        # Request the file content
        request = service.files().get_media(fileId=file_id)
        file_stream = io.BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request)

        done = False
        while not done:
            status, done = downloader.next_chunk()

        # Move to the beginning of the stream
        file_stream.seek(0)

        # Return the file as a downloadable response
        response = HttpResponse(file_stream, content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{file_name}"'
        return response

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)