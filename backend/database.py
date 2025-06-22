from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager

# SQLite database URL
SQLALCHEMY_DATABASE_URL = "sqlite:///./chat_app.db"

# Create the SQLAlchemy engine with more generous pooling settings
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False},
    pool_size=20,  # Increase pool size
    max_overflow=20,  # Allow more overflow connections
    pool_timeout=60,  # Increase timeout
    pool_recycle=3600,  # Recycle connections after 1 hour
    pool_pre_ping=True  # Check connection validity before using it
)

# Create a SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create a Base class for declarative models
Base = declarative_base()

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Context manager for getting a DB session
@contextmanager
def get_db_context():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
