# database/session.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# For production, read the database path from an environment variable.
# For local development, it falls back to the original "sqlite:///./jobs.db".
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./jobs.db")

# Add a print statement to be 100% sure which database is being used.
print(f"💽 Connecting to database at: {DATABASE_URL}")

# create_engine is the entry point to the database
# connect_args is needed only for SQLite to allow multithreading
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)

# Each instance of SessionLocal will be a database session.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for our declarative models
Base = declarative_base()

# Function to create all tables in the database
def init_db():
    print("Initializing database and creating tables (if they don't exist)...")
    # This will create tables for all models that inherit from Base
    from database.models import Job  # Import model here
    # THIS IS THE FIX: checkfirst=True tells SQLAlchemy to check for the table's existence before trying to create it.
    Base.metadata.create_all(bind=engine, checkfirst=True)
    print("Database initialized.") 