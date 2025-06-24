import os
import logging
import time  # <--- Add this
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import OperationalError  # <--- Add this

# Get the database URL from environment variables
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./jobs.db")

# Hide sensitive parts of the URL for logging
log_db_url = DATABASE_URL.split('@')[-1] if "@" in DATABASE_URL else DATABASE_URL
logging.info(f"💽 Connecting to database at: {log_db_url}")

engine_args = {}
if DATABASE_URL.startswith("sqlite"):
    engine_args['connect_args'] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def init_db():
    """
    Initializes the database with a retry mechanism for initial connection.
    This is crucial for cloud environments where services may start at different times.
    """
    logging.info("Attempting to initialize database tables...")

    max_retries = 10
    retry_delay_seconds = 5
    for attempt in range(max_retries):
        try:
            # The connection attempt happens here
            with engine.connect() as connection:
                logging.info("Database connection successful.")
                
                # For PostgreSQL, use a lock to prevent race conditions between workers
                if DATABASE_URL.startswith("postgres"):
                    with connection.begin():
                        connection.execute(text("SELECT pg_advisory_xact_lock(12345)"))
                        logging.info("Acquired DB lock. Checking schema...")
                        from database.models import User, Job
                        Base.metadata.create_all(bind=engine, checkfirst=True)
                        logging.info("Schema check/creation complete. Releasing lock.")
                else: # For SQLite or other DBs
                    from database.models import User, Job
                    Base.metadata.create_all(bind=engine, checkfirst=True)

                logging.info("Database initialization process finished successfully.")
                return  # Exit the function on success

        except OperationalError as e:
            logging.warning(f"DB connection failed (Attempt {attempt + 1}/{max_retries}): {e}. Retrying in {retry_delay_seconds}s...")
            time.sleep(retry_delay_seconds)
        except Exception as e:
            logging.error(f"An unexpected error occurred during DB initialization: {e}", exc_info=True)
            # On other errors, it's better to fail fast
            raise e
            
    # If the loop completes without connecting, raise an exception
    raise Exception("Could not establish database connection after multiple retries. Aborting application startup.")