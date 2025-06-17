# File: celery_worker.py (in the root directory)
import os
from celery import Celery
from dotenv import load_dotenv

# Load .env file for local development
load_dotenv()

# --- MODIFIED FOR RENDER ---
# Render provides the REDIS_URL environment variable automatically when services are linked.
# We fall back to the local .env variable for development.
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create the Celery app instance
# The first argument is the name of the current module.
# The `broker` argument specifies the URL of the message broker (Redis).
# The `backend` argument is used to store task results. We'll also use Redis for this.
celery_app = Celery(
    "tasks",
    broker=redis_url,
    backend=redis_url
)

# Optional: Configure Celery to automatically discover tasks
# It will look for tasks in a file named `tasks.py` inside any installed apps.
# For our structure, we will explicitly define the task path.
celery_app.conf.update(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    timezone='UTC',
    enable_utc=True,
)

# This is where we will tell Celery where to find our task function.
# We will create this file in the next step.
celery_app.autodiscover_tasks(['src.tasks']) 