# File: database/session.py (REVISED)

import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# Get the database URL from environment variables, defaulting to SQLite for local dev
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./jobs.db")

# Hide sensitive parts of the URL for logging
if "@" in DATABASE_URL:
    log_db_url = DATABASE_URL.split('@')[-1]
else:
    log_db_url = DATABASE_URL
logging.info(f"💽 Connecting to database at: {log_db_url}")

# --- THIS IS THE CORRECTED LOGIC ---
# Prepare keyword arguments for create_engine
engine_args = {}

# Only add the connect_args if we are using SQLite.
if DATABASE_URL.startswith("sqlite"):
    engine_args['connect_args'] = {"check_same_thread": False}

# Create the engine, unpacking the arguments dictionary.
# If it's not SQLite, the dictionary will be empty and no extra args are passed.
engine = create_engine(DATABASE_URL, **engine_args)


# --- The rest of the file is unchanged ---
# Each instance of SessionLocal will be a database session.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for our declarative models
Base = declarative_base()

# Function to create all tables in the database
def init_db():
    """
    Initializes the database. Uses a PostgreSQL advisory lock to prevent
    race conditions when multiple gunicorn workers start simultaneously.
    """
    logging.info("Attempting to initialize database tables...")

    # For non-PostgreSQL databases (like SQLite), just run the command.
    if not DATABASE_URL.startswith("postgres"):
        from database.models import User, Job
        Base.metadata.create_all(bind=engine, checkfirst=True)
        logging.info("Database initialized (SQLite).")
        return

    # For PostgreSQL, use a lock.
    # The number 12345 is an arbitrary lock ID. Any integer will do.
    with engine.connect() as connection:
        with connection.begin(): # Start a transaction
            # Try to acquire a session-level advisory lock.
            # This will block until the lock is available.
            connection.execute(text("SELECT pg_advisory_xact_lock(12345)"))
            
            logging.info("Acquired DB lock. Checking schema...")
            
            # Now that we have the lock, we can safely create tables.
            from database.models import User, Job
            Base.metadata.create_all(bind=engine, checkfirst=True)
            
            logging.info("Schema check/creation complete. Releasing lock.")
        # The lock is automatically released when the transaction block ends.
    logging.info("Database initialization process finished.")