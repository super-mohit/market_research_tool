# File: database/session.py (Corrected Version)

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# Get the database URL from environment variables, defaulting to SQLite for local dev
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./jobs.db")

# Hide sensitive parts of the URL for logging
if "@" in DATABASE_URL:
    log_db_url = DATABASE_URL.split('@')[-1]
else:
    log_db_url = DATABASE_URL

print(f"💽 Connecting to database at: {log_db_url}")

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
    print("Initializing database and creating tables (if they don't exist)...")
    # This will create tables for all models that inherit from Base
    from database.models import Job, User  # Import models here
    Base.metadata.create_all(bind=engine, checkfirst=True)
    print("Database initialized.")