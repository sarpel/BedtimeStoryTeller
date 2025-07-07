"""
SQLite database models for storing stories, sessions, and configuration.
Uses SQLAlchemy ORM with async support and Pydantic for validation.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, Float, JSON,
    ForeignKey, Index, create_engine
)
from sqlalchemy.orm import relationship, selectinload
from sqlalchemy.sql import func
from pydantic import BaseModel, Field, field_validator
import aiosqlite

logger = logging.getLogger(__name__)

Base = declarative_base()


class Story(Base):
    """Story database model."""
    __tablename__ = "stories"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    prompt = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    language = Column(String(10), default="tr", nullable=False)
    age_rating = Column(String(20), default="5+", nullable=False)
    word_count = Column(Integer, default=0)
    estimated_duration = Column(Float, default=0.0)  # minutes
    themes = Column(JSON, default=list)  # List of themes
    characters = Column(JSON, default=list)  # List of characters
    safety_rating = Column(JSON, default=dict)  # Safety rating info
    provider_used = Column(String(50), nullable=True)  # LLM provider
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_favorite = Column(Boolean, default=False)
    play_count = Column(Integer, default=0)
    last_played = Column(DateTime, nullable=True)
    
    # Relationships
    sessions = relationship("StorySession", back_populates="story")
    
    # Indexes
    __table_args__ = (
        Index('idx_story_language', 'language'),
        Index('idx_story_age_rating', 'age_rating'),
        Index('idx_story_created', 'created_at'),
        Index('idx_story_favorite', 'is_favorite'),
        Index('idx_story_play_count', 'play_count'),
    )


class StorySession(Base):
    """Story session/playback model."""
    __tablename__ = "story_sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(50), unique=True, nullable=False)
    story_id = Column(Integer, ForeignKey("stories.id"), nullable=True)
    prompt = Column(Text, nullable=False)
    language = Column(String(10), default="tr")
    age_rating = Column(String(20), default="5+")
    start_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    end_time = Column(DateTime, nullable=True)
    duration = Column(Float, nullable=True)  # seconds
    paragraphs_generated = Column(Integer, default=0)
    paragraphs_played = Column(Integer, default=0)
    total_audio_duration = Column(Float, default=0.0)  # seconds
    status = Column(String(20), default="active")  # active, completed, failed, stopped
    wakeword_trigger = Column(String(50), nullable=True)  # wake word that triggered
    llm_provider = Column(String(50), nullable=True)
    tts_provider = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    session_metadata = Column(JSON, default=dict)  # Additional session data
    
    # Relationships
    story = relationship("Story", back_populates="sessions")
    
    # Indexes
    __table_args__ = (
        Index('idx_session_start_time', 'start_time'),
        Index('idx_session_status', 'status'),
        Index('idx_session_story_id', 'story_id'),
    )


class UserPreferences(Base):
    """User preferences and settings."""
    __tablename__ = "user_preferences"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(JSON, nullable=True)
    value_type = Column(String(20), default="string")  # string, int, float, bool, json
    description = Column(Text, nullable=True)
    category = Column(String(50), default="general")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        Index('idx_pref_category', 'category'),
        Index('idx_pref_key', 'key'),
    )


class ScheduledStory(Base):
    """Scheduled story playback."""
    __tablename__ = "scheduled_stories"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    story_id = Column(Integer, ForeignKey("stories.id"), nullable=True)
    prompt = Column(Text, nullable=True)  # Use if no specific story
    schedule_time = Column(String(10), nullable=False)  # HH:MM format
    days_of_week = Column(JSON, default=list)  # [0-6] where 0=Monday
    is_enabled = Column(Boolean, default=True)
    language = Column(String(10), default="tr")
    age_rating = Column(String(20), default="5+")
    volume = Column(Float, default=0.7)  # 0.0 to 1.0
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_triggered = Column(DateTime, nullable=True)
    
    # Relationships
    story = relationship("Story")
    
    # Indexes
    __table_args__ = (
        Index('idx_schedule_enabled', 'is_enabled'),
        Index('idx_schedule_time', 'schedule_time'),
    )


class SystemEvent(Base):
    """System events and logs."""
    __tablename__ = "system_events"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), nullable=False)  # startup, shutdown, error, wake_word, etc.
    message = Column(Text, nullable=False)
    level = Column(String(20), default="info")  # debug, info, warning, error, critical
    component = Column(String(50), nullable=True)  # which component generated the event
    session_id = Column(String(50), nullable=True)  # related session if any
    event_metadata = Column(JSON, default=dict)  # additional event data
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Indexes
    __table_args__ = (
        Index('idx_event_timestamp', 'timestamp'),
        Index('idx_event_type', 'event_type'),
        Index('idx_event_level', 'level'),
    )


# Pydantic models for validation and API responses

class StoryCreate(BaseModel):
    """Pydantic model for creating a new story."""
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=10)
    prompt: Optional[str] = None
    summary: Optional[str] = None
    language: str = Field(default="tr", pattern=r"^(tr|en)$")
    age_rating: str = Field(default="5+", pattern=r"^\d+\+$")
    themes: List[str] = Field(default_factory=list)
    characters: List[str] = Field(default_factory=list)
    
    @field_validator('content')
    @classmethod
    def validate_content_length(cls, v):
        if len(v) > 10000:  # Reasonable limit for story length
            raise ValueError("Story content too long")
        return v


class StoryUpdate(BaseModel):
    """Pydantic model for updating a story."""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = Field(None, min_length=10)
    summary: Optional[str] = None
    themes: Optional[List[str]] = None
    characters: Optional[List[str]] = None
    is_favorite: Optional[bool] = None


class StoryResponse(BaseModel):
    """Pydantic model for story API responses."""
    id: int
    title: str
    content: str
    prompt: Optional[str]
    summary: Optional[str]
    language: str
    age_rating: str
    word_count: int
    estimated_duration: float
    themes: List[str]
    characters: List[str]
    safety_rating: Dict[str, Any]
    provider_used: Optional[str]
    created_at: datetime
    updated_at: datetime
    is_favorite: bool
    play_count: int
    last_played: Optional[datetime]
    
    class Config:
        from_attributes = True


class SessionCreate(BaseModel):
    """Pydantic model for creating a story session."""
    prompt: str = Field(..., min_length=1)
    language: str = Field(default="tr", pattern=r"^(tr|en)$")
    age_rating: str = Field(default="5+", pattern=r"^\d+\+$")
    wakeword_trigger: Optional[str] = None


class SessionResponse(BaseModel):
    """Pydantic model for session API responses."""
    id: int
    session_id: str
    story_id: Optional[int]
    prompt: str
    language: str
    age_rating: str
    start_time: datetime
    end_time: Optional[datetime]
    duration: Optional[float]
    paragraphs_generated: int
    paragraphs_played: int
    total_audio_duration: float
    status: str
    wakeword_trigger: Optional[str]
    llm_provider: Optional[str]
    tts_provider: Optional[str]
    error_message: Optional[str]
    
    class Config:
        from_attributes = True


class ScheduledStoryCreate(BaseModel):
    """Pydantic model for creating a scheduled story."""
    name: str = Field(..., min_length=1, max_length=100)
    story_id: Optional[int] = None
    prompt: Optional[str] = None
    schedule_time: str = Field(..., pattern=r"^([01]?\d|2[0-3]):[0-5]\d$")
    days_of_week: List[int] = Field(..., min_items=1)
    language: str = Field(default="tr", pattern=r"^(tr|en)$")
    age_rating: str = Field(default="5+", pattern=r"^\d+\+$")
    volume: float = Field(default=0.7, ge=0.0, le=1.0)
    
    @field_validator('days_of_week')
    @classmethod
    def validate_days(cls, v):
        if not all(0 <= day <= 6 for day in v):
            raise ValueError("Days of week must be between 0-6")
        return sorted(list(set(v)))  # Remove duplicates and sort
    
    @field_validator('story_id', 'prompt')
    @classmethod
    def validate_story_or_prompt(cls, v, values):
        if not values.get('story_id') and not v:
            raise ValueError("Either story_id or prompt must be provided")
        return v


class UserPreferenceUpdate(BaseModel):
    """Pydantic model for updating user preferences."""
    value: Any
    description: Optional[str] = None


# Database utility functions

async def create_database_engine(database_url: str):
    """Create async database engine."""
    try:
        # For SQLite with aiosqlite
        engine = create_async_engine(
            database_url,
            echo=False,  # Set to True for SQL debugging
            pool_pre_ping=True,
            pool_recycle=3600  # Recycle connections after 1 hour
        )
        return engine
    except Exception as e:
        logger.error(f"Failed to create database engine: {e}")
        raise


async def create_tables(engine):
    """Create all database tables."""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}")
        raise


async def get_database_session(engine) -> AsyncSession:
    """Get database session."""
    SessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    return SessionLocal()


async def init_default_preferences(session: AsyncSession):
    """Initialize default user preferences."""
    default_preferences = [
        {
            "key": "default_language",
            "value": "tr",
            "value_type": "string",
            "description": "Default story language",
            "category": "story"
        },
        {
            "key": "default_age_rating", 
            "value": "5+",
            "value_type": "string",
            "description": "Default age rating for stories",
            "category": "story"
        },
        {
            "key": "max_story_paragraphs",
            "value": 10,
            "value_type": "int", 
            "description": "Maximum paragraphs per story",
            "category": "story"
        },
        {
            "key": "default_volume",
            "value": 0.7,
            "value_type": "float",
            "description": "Default audio volume",
            "category": "audio"
        },
        {
            "key": "wakeword_engine",
            "value": "porcupine",
            "value_type": "string",
            "description": "Active wakeword engine",
            "category": "wakeword"
        },
        {
            "key": "do_not_disturb_enabled",
            "value": False,
            "value_type": "bool",
            "description": "Do not disturb mode enabled",
            "category": "system"
        },
        {
            "key": "do_not_disturb_start",
            "value": "22:00",
            "value_type": "string",
            "description": "Do not disturb start time",
            "category": "system"
        },
        {
            "key": "do_not_disturb_end",
            "value": "07:00", 
            "value_type": "string",
            "description": "Do not disturb end time",
            "category": "system"
        },
        {
            "key": "auto_save_stories",
            "value": True,
            "value_type": "bool",
            "description": "Automatically save generated stories",
            "category": "storage"
        }
    ]
    
    try:
        from sqlalchemy import select
        
        for pref_data in default_preferences:
            # Check if preference already exists
            result = await session.execute(
                select(UserPreferences).where(UserPreferences.key == pref_data["key"])
            )
            existing = result.scalar_one_or_none()
            
            if not existing:
                preference = UserPreferences(**pref_data)
                session.add(preference)
        
        await session.commit()
        logger.info("Default preferences initialized")
        
    except Exception as e:
        logger.error(f"Failed to initialize default preferences: {e}")
        await session.rollback()
        raise