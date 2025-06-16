import os
from dotenv import load_dotenv

# Load environment variables from the .env file in the project root
# This line looks for the .env file in the parent directory of src/
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

# --- API Keys ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")

# --- RAG API Config ---
RAG_API_BASE_URL = os.getenv("RAG_API_BASE_URL")
RAG_API_TOKEN = os.getenv("RAG_API_TOKEN")
RAG_API_ORG_ID = os.getenv("RAG_API_ORG_ID")
RAG_API_USER_TYPE = os.getenv("RAG_API_USER_TYPE")

# --- Startup Banner ---
def _mask_key(key_value: str | None) -> str:
    """Mask API key for display, showing only first 4 and last 4 characters."""
    if not key_value:
        return "❌ NOT SET"
    if len(key_value) <= 8:
        return "✅ SET (short)"
    return f"✅ SET ({key_value[:4]}...{key_value[-4:]})"

print("\n" + "="*60)
print("🔧 MARKET INTELLIGENCE AGENT - Environment Status")
print("="*60)
print(f"GEMINI_API_KEY:  {_mask_key(GEMINI_API_KEY)}")
print(f"GOOGLE_API_KEY:  {_mask_key(GOOGLE_API_KEY)}")
print(f"GOOGLE_CSE_ID:   {_mask_key(GOOGLE_CSE_ID)}")
print("-" * 60)
print("🔌 RAG Uploader Status")
print(f"RAG_API_BASE_URL:    {RAG_API_BASE_URL or '❌ NOT SET'}")
print(f"RAG_API_TOKEN: {_mask_key(RAG_API_TOKEN)}")
print(f"RAG_API_ORG_ID:      {RAG_API_ORG_ID or '❌ NOT SET'}")
print("="*60 + "\n")

# --- Validation ---
def assert_all_env():
    if not all([GEMINI_API_KEY, GOOGLE_API_KEY, GOOGLE_CSE_ID]):
        raise ValueError("Missing env vars: set GEMINI_API_KEY, GOOGLE_API_KEY, GOOGLE_CSE_ID")

def assert_rag_env():
    """Checks if all required RAG environment variables are set."""
    if not all([RAG_API_BASE_URL, RAG_API_TOKEN, RAG_API_ORG_ID, RAG_API_USER_TYPE]):
        raise ValueError("Missing env vars for RAG Uploader: set RAG_API_BASE_URL, RAG_API_TOKEN, RAG_API_ORG_ID, and RAG_API_USER_TYPE")

# You can add other configurations here later
# For example:
# LLM_PLANNER_MODEL = "gemini-1.5-pro-latest"
# LLM_SYNTHESIZER_MODEL = "gemini-1.5-flash-latest"