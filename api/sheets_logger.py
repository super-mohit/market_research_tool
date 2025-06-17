import requests
import os
import logging
import threading

# Get the URL from environment variables
SHEETS_WEB_APP_URL = os.getenv("SHEETS_WEB_APP_URL")

def log_event(event: str, user_id: str = None, job_id: str = None, query: str = None, details: dict = None):
    """
    Sends a log event to a Google Sheets Web App.
    Runs in a non-blocking background thread.
    """
    if not SHEETS_WEB_APP_URL:
        # Log a warning if the feature is used but not configured
        logging.warning("SHEETS_WEB_APP_URL is not set. Skipping Google Sheets logging.")
        return

    payload = {
        "event": event,
        "userId": user_id,
        "jobId": job_id,
        "query": query,
        "details": details or {}
    }
    
    def send_request():
        """The function that will run in the background thread."""
        try:
            response = requests.post(SHEETS_WEB_APP_URL, json=payload, timeout=10)
            response.raise_for_status()
            logging.info(f"Successfully logged event '{event}' to Google Sheets.")
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to log event to Google Sheets: {e}")

    # Run the request in a daemon thread so it doesn't block the API response
    thread = threading.Thread(target=send_request, daemon=True)
    thread.start() 