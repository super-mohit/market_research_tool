# src/utils/gdrive_uploader.py
import os
import logging
from io import BytesIO
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# The path to your service account key file
# Render will place the secret file at this path.
SERVICE_ACCOUNT_FILE = 'gdrive_service_account.json'
# The scopes define the permissions we are requesting.
SCOPES = ['https://www.googleapis.com/auth/drive']
# The ID of the folder in Google Drive where PDFs will be uploaded.
PARENT_FOLDER_ID = os.getenv("GDRIVE_PARENT_FOLDER_ID")

def get_drive_service():
    """Initializes and returns a Google Drive API service object."""
    try:
        if not os.path.exists(SERVICE_ACCOUNT_FILE):
            logging.error(f"Google Drive service account file not found at '{SERVICE_ACCOUNT_FILE}'")
            return None
        
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        service = build('drive', 'v3', credentials=creds)
        return service
    except Exception as e:
        logging.error(f"Failed to initialize Google Drive service: {e}", exc_info=True)
        return None

def upload_pdf_to_gdrive(pdf_bytes: bytes, file_name: str) -> str | None:
    """
    Uploads a PDF byte stream to the configured Google Drive folder.

    Args:
        pdf_bytes: The PDF content as bytes.
        file_name: The desired name for the file in Google Drive.

    Returns:
        The permanent, shareable URL of the uploaded file, or None on failure.
    """
    service = get_drive_service()
    if not service or not PARENT_FOLDER_ID:
        logging.error("Google Drive service or parent folder ID is not configured.")
        return None

    try:
        file_metadata = {
            'name': file_name,
            'parents': [PARENT_FOLDER_ID]
        }
        
        media = MediaIoBaseUpload(BytesIO(pdf_bytes), mimetype='application/pdf', resumable=True)
        
        # Create the file and upload content
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()

        file_id = file.get('id')
        
        # Make the file publicly readable
        service.permissions().create(
            fileId=file_id,
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()

        # The webViewLink is the direct, shareable URL
        shareable_link = file.get('webViewLink')
        logging.info(f"Successfully uploaded PDF to Google Drive. Link: {shareable_link}")
        return shareable_link

    except Exception as e:
        logging.error(f"Failed to upload PDF to Google Drive: {e}", exc_info=True)
        return None 