# -------------------------------------------------
#  Global throttling & limit switches for the pipeline
# -------------------------------------------------
MAX_SEARCH_RESULTS   = 9        # items per Google-CSE query
MAX_SEARCH_WORKERS   = 9    # parallel threads for CSE calls

MAX_GENERAL_FOR_REPORT = 27  # cap "General" URLs that feed the executive report

MAX_PER_BUCKET_EXTRACT = 9   # News / Patents / Conf / Legalnews
EXTRACT_BATCH_SIZE     = 18  # 2 × batches → 18 URLs each
MAX_GEMINI_PARALLEL    = 18  # concurrent Gemini requests in extractor

# ---- NEW ----  Global “freshness” policy -------------------------
RECENT_YEARS = 2             # only keep items from the last N calendar years
