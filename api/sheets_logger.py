import requests
import os
import logging
import threading
import json

# Get the URL from environment variables
SHEETS_WEB_APP_URL = os.getenv("SHEETS_WEB_APP_URL")

def log_to_sheets(**kwargs):
    """
    Sends a structured log event to a Google Sheets Web App.
    Runs in a non-blocking background thread.
    Accepts keyword arguments that match the Google Sheet columns.
    """
    if not SHEETS_WEB_APP_URL:
        if "eventType" in kwargs and kwargs["eventType"] == "user_signup": # Only warn once to prevent spam
             logging.warning("SHEETS_WEB_APP_URL is not set. Skipping Google Sheets logging.")
        return

    # Whitelist of expected keys to match our Apps Script
    allowed_keys = {
        "eventType", "userId", "userEmail", "jobId", "ragCollection",
        "query", "status", "stage", "details", "errorMessage"
    }
    
    payload = {k: v for k, v in kwargs.items() if k in allowed_keys and v is not None}

    def send_request():
        try:
            # The payload is already a dict, so we can send it as json
            response = requests.post(SHEETS_WEB_APP_URL, json=payload, timeout=10)
            response.raise_for_status()
            logging.info(f"Successfully logged event '{payload.get('eventType')}' to Google Sheets.")
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to log event to Google Sheets: {e}")

    thread = threading.Thread(target=send_request, daemon=True)
    thread.start()

# Keep the old function for backward compatibility, but have it call the new one
def log_event(event: str, user_id: str = None, job_id: str = None, query: str = None, details: dict = None):
    """
    Legacy function for backward compatibility.
    Maps old parameters to the new log_to_sheets function.
    """
    log_to_sheets(
        eventType=event,
        userId=user_id,
        jobId=job_id,
        query=query,
        details=details
    ) 