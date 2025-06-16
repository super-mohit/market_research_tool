# database/session.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# The database file will be created in the project root
DATABASE_URL = "sqlite:///./jobs.db"

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
    print("Initializing database and creating tables...")
    # This will create tables for all models that inherit from Base
    from database.models import Job  # Import model here
    Base.metadata.create_all(bind=engine)
    print("Database initialized.") 