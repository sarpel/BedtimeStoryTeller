"""
Story library management with CRUD operations.
Provides async database operations for stories, sessions, and preferences.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, asc
from sqlalchemy.orm import selectinload

from .models import (
    Story, StorySession, UserPreferences, ScheduledStory, SystemEvent,
    StoryCreate, StoryUpdate, StoryResponse, SessionCreate, SessionResponse,
    ScheduledStoryCreate, UserPreferenceUpdate
)

logger = logging.getLogger(__name__)


class StoryLibrary:
    """
    Story library manager providing CRUD operations and search functionality.
    Handles stories, sessions, preferences, and system events.
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    # Story operations
    
    async def create_story(self, story_data: StoryCreate, metadata: Optional[Dict[str, Any]] = None) -> Story:
        """Create a new story."""
        try:
            story_dict = story_data.dict()
            
            # Add metadata if provided
            if metadata:
                story_dict.update({
                    "word_count": metadata.get("word_count", 0),
                    "estimated_duration": metadata.get("estimated_duration", 0.0),
                    "safety_rating": metadata.get("safety_rating", {}),
                    "provider_used": metadata.get("provider_used")
                })
            
            story = Story(**story_dict)
            self.session.add(story)
            await self.session.commit()
            await self.session.refresh(story)
            
            logger.info(f"Created story: {story.id} - {story.title}")
            return story
            
        except Exception as e:
            logger.error(f"Failed to create story: {e}")
            await self.session.rollback()
            raise
    
    async def get_story(self, story_id: int) -> Optional[Story]:
        """Get a story by ID."""
        try:
            result = await self.session.execute(
                select(Story).where(Story.id == story_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to get story {story_id}: {e}")
            return None
    
    async def update_story(self, story_id: int, story_data: StoryUpdate) -> Optional[Story]:
        """Update an existing story."""
        try:
            story = await self.get_story(story_id)
            if not story:
                return None
            
            update_data = story_data.dict(exclude_unset=True)
            for field, value in update_data.items():
                setattr(story, field, value)
            
            story.updated_at = datetime.utcnow()
            await self.session.commit()
            await self.session.refresh(story)
            
            logger.info(f"Updated story: {story.id}")
            return story
            
        except Exception as e:
            logger.error(f"Failed to update story {story_id}: {e}")
            await self.session.rollback()
            raise
    
    async def delete_story(self, story_id: int) -> bool:
        """Delete a story."""
        try:
            story = await self.get_story(story_id)
            if not story:
                return False
            
            await self.session.delete(story)
            await self.session.commit()
            
            logger.info(f"Deleted story: {story_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete story {story_id}: {e}")
            await self.session.rollback()
            raise
    
    async def search_stories(
        self,
        query: Optional[str] = None,
        language: Optional[str] = None,
        age_rating: Optional[str] = None,
        themes: Optional[List[str]] = None,
        is_favorite: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: str = "desc"
    ) -> Tuple[List[Story], int]:
        """
        Search stories with filters and pagination.
        
        Returns:
            Tuple of (stories, total_count)
        """
        try:
            # Build query
            query_filters = []
            
            if query:
                # Search in title, content, and prompt
                search_filter = or_(
                    Story.title.ilike(f"%{query}%"),
                    Story.content.ilike(f"%{query}%"),
                    Story.prompt.ilike(f"%{query}%")
                )
                query_filters.append(search_filter)
            
            if language:
                query_filters.append(Story.language == language)
            
            if age_rating:
                query_filters.append(Story.age_rating == age_rating)
            
            if themes:
                # Search for stories containing any of the specified themes
                theme_filters = []
                for theme in themes:
                    theme_filters.append(Story.themes.like(f'%"{theme}"%'))
                query_filters.append(or_(*theme_filters))
            
            if is_favorite is not None:
                query_filters.append(Story.is_favorite == is_favorite)
            
            # Build base query
            base_query = select(Story)
            if query_filters:
                base_query = base_query.where(and_(*query_filters))
            
            # Get total count
            count_query = select(func.count(Story.id))
            if query_filters:
                count_query = count_query.where(and_(*query_filters))
            
            count_result = await self.session.execute(count_query)
            total_count = count_result.scalar()
            
            # Apply sorting
            sort_column = getattr(Story, sort_by, Story.created_at)
            if sort_order.lower() == "desc":
                base_query = base_query.order_by(desc(sort_column))
            else:
                base_query = base_query.order_by(asc(sort_column))
            
            # Apply pagination
            base_query = base_query.offset(offset).limit(limit)
            
            # Execute query
            result = await self.session.execute(base_query)
            stories = result.scalars().all()
            
            return stories, total_count
            
        except Exception as e:
            logger.error(f"Failed to search stories: {e}")
            return [], 0
    
    async def get_popular_stories(self, limit: int = 10) -> List[Story]:
        """Get most popular stories by play count."""
        try:
            result = await self.session.execute(
                select(Story)
                .where(Story.play_count > 0)
                .order_by(desc(Story.play_count), desc(Story.created_at))
                .limit(limit)
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Failed to get popular stories: {e}")
            return []
    
    async def get_recent_stories(self, limit: int = 10) -> List[Story]:
        """Get most recently created stories."""
        try:
            result = await self.session.execute(
                select(Story)
                .order_by(desc(Story.created_at))
                .limit(limit)
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Failed to get recent stories: {e}")
            return []
    
    async def get_favorite_stories(self, limit: int = 50) -> List[Story]:
        """Get favorite stories."""
        try:
            result = await self.session.execute(
                select(Story)
                .where(Story.is_favorite == True)
                .order_by(desc(Story.last_played), desc(Story.created_at))
                .limit(limit)
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Failed to get favorite stories: {e}")
            return []
    
    async def increment_play_count(self, story_id: int) -> None:
        """Increment play count and update last played time."""
        try:
            story = await self.get_story(story_id)
            if story:
                story.play_count += 1
                story.last_played = datetime.utcnow()
                await self.session.commit()
        except Exception as e:
            logger.error(f"Failed to increment play count for story {story_id}: {e}")
    
    # Session operations
    
    async def create_session(self, session_data: SessionCreate) -> StorySession:
        """Create a new story session."""
        try:
            import time
            session_dict = session_data.dict()
            session_dict["session_id"] = f"session_{int(time.time())}"
            
            session = StorySession(**session_dict)
            self.session.add(session)
            await self.session.commit()
            await self.session.refresh(session)
            
            logger.info(f"Created session: {session.session_id}")
            return session
            
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            await self.session.rollback()
            raise
    
    async def update_session(self, session_id: str, **updates) -> Optional[StorySession]:
        """Update a session with arbitrary fields."""
        try:
            result = await self.session.execute(
                select(StorySession).where(StorySession.session_id == session_id)
            )
            session = result.scalar_one_or_none()
            
            if not session:
                return None
            
            for field, value in updates.items():
                if hasattr(session, field):
                    setattr(session, field, value)
            
            await self.session.commit()
            await self.session.refresh(session)
            return session
            
        except Exception as e:
            logger.error(f"Failed to update session {session_id}: {e}")
            await self.session.rollback()
            raise
    
    async def complete_session(self, session_id: str, story_id: Optional[int] = None) -> None:
        """Mark a session as completed."""
        try:
            updates = {
                "status": "completed",
                "end_time": datetime.utcnow()
            }
            if story_id:
                updates["story_id"] = story_id
            
            session = await self.update_session(session_id, **updates)
            if session and session.end_time and session.start_time:
                duration = (session.end_time - session.start_time).total_seconds()
                await self.update_session(session_id, duration=duration)
                
        except Exception as e:
            logger.error(f"Failed to complete session {session_id}: {e}")
    
    async def get_recent_sessions(self, limit: int = 20) -> List[StorySession]:
        """Get recent story sessions."""
        try:
            result = await self.session.execute(
                select(StorySession)
                .options(selectinload(StorySession.story))
                .order_by(desc(StorySession.start_time))
                .limit(limit)
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Failed to get recent sessions: {e}")
            return []
    
    async def get_session_stats(self, days: int = 30) -> Dict[str, Any]:
        """Get session statistics for the last N days."""
        try:
            since_date = datetime.utcnow() - timedelta(days=days)
            
            # Total sessions
            total_result = await self.session.execute(
                select(func.count(StorySession.id))
                .where(StorySession.start_time >= since_date)
            )
            total_sessions = total_result.scalar()
            
            # Completed sessions
            completed_result = await self.session.execute(
                select(func.count(StorySession.id))
                .where(
                    and_(
                        StorySession.start_time >= since_date,
                        StorySession.status == "completed"
                    )
                )
            )
            completed_sessions = completed_result.scalar()
            
            # Average duration
            duration_result = await self.session.execute(
                select(func.avg(StorySession.duration))
                .where(
                    and_(
                        StorySession.start_time >= since_date,
                        StorySession.duration.isnot(None)
                    )
                )
            )
            avg_duration = duration_result.scalar() or 0
            
            # Wake word triggers
            wakeword_result = await self.session.execute(
                select(func.count(StorySession.id))
                .where(
                    and_(
                        StorySession.start_time >= since_date,
                        StorySession.wakeword_trigger.isnot(None)
                    )
                )
            )
            wakeword_sessions = wakeword_result.scalar()
            
            return {
                "days": days,
                "total_sessions": total_sessions,
                "completed_sessions": completed_sessions,
                "completion_rate": completed_sessions / total_sessions if total_sessions > 0 else 0,
                "average_duration_seconds": avg_duration,
                "wakeword_triggered_sessions": wakeword_sessions,
                "wakeword_trigger_rate": wakeword_sessions / total_sessions if total_sessions > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Failed to get session stats: {e}")
            return {}
    
    # User preferences
    
    async def get_preference(self, key: str) -> Optional[Any]:
        """Get a user preference value."""
        try:
            result = await self.session.execute(
                select(UserPreferences).where(UserPreferences.key == key)
            )
            pref = result.scalar_one_or_none()
            return pref.value if pref else None
        except Exception as e:
            logger.error(f"Failed to get preference {key}: {e}")
            return None
    
    async def set_preference(self, key: str, value: Any, description: Optional[str] = None) -> None:
        """Set a user preference."""
        try:
            result = await self.session.execute(
                select(UserPreferences).where(UserPreferences.key == key)
            )
            pref = result.scalar_one_or_none()
            
            if pref:
                pref.value = value
                pref.updated_at = datetime.utcnow()
                if description:
                    pref.description = description
            else:
                # Determine value type
                value_type = type(value).__name__
                if value_type == "list" or value_type == "dict":
                    value_type = "json"
                
                pref = UserPreferences(
                    key=key,
                    value=value,
                    value_type=value_type,
                    description=description or f"User preference: {key}"
                )
                self.session.add(pref)
            
            await self.session.commit()
            
        except Exception as e:
            logger.error(f"Failed to set preference {key}: {e}")
            await self.session.rollback()
            raise
    
    async def get_preferences_by_category(self, category: str) -> Dict[str, Any]:
        """Get all preferences in a category."""
        try:
            result = await self.session.execute(
                select(UserPreferences).where(UserPreferences.category == category)
            )
            prefs = result.scalars().all()
            return {pref.key: pref.value for pref in prefs}
        except Exception as e:
            logger.error(f"Failed to get preferences for category {category}: {e}")
            return {}
    
    # Scheduled stories
    
    async def create_scheduled_story(self, schedule_data: ScheduledStoryCreate) -> ScheduledStory:
        """Create a new scheduled story."""
        try:
            schedule = ScheduledStory(**schedule_data.dict())
            self.session.add(schedule)
            await self.session.commit()
            await self.session.refresh(schedule)
            
            logger.info(f"Created scheduled story: {schedule.id} - {schedule.name}")
            return schedule
            
        except Exception as e:
            logger.error(f"Failed to create scheduled story: {e}")
            await self.session.rollback()
            raise
    
    async def get_active_schedules(self) -> List[ScheduledStory]:
        """Get all active scheduled stories."""
        try:
            result = await self.session.execute(
                select(ScheduledStory)
                .where(ScheduledStory.is_enabled == True)
                .options(selectinload(ScheduledStory.story))
                .order_by(ScheduledStory.schedule_time)
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Failed to get active schedules: {e}")
            return []
    
    async def update_schedule_trigger(self, schedule_id: int) -> None:
        """Update the last triggered time for a schedule."""
        try:
            result = await self.session.execute(
                select(ScheduledStory).where(ScheduledStory.id == schedule_id)
            )
            schedule = result.scalar_one_or_none()
            
            if schedule:
                schedule.last_triggered = datetime.utcnow()
                await self.session.commit()
                
        except Exception as e:
            logger.error(f"Failed to update schedule trigger {schedule_id}: {e}")
    
    # System events
    
    async def log_event(
        self,
        event_type: str,
        message: str,
        level: str = "info",
        component: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log a system event."""
        try:
            # Skip logging if session is in flush process to avoid concurrent operation warnings
            if hasattr(self.session, '_flushing') and self.session._flushing:
                logger.debug(f"Skipping event logging during session flush: {event_type}")
                return
                
            event = SystemEvent(
                event_type=event_type,
                message=message,
                level=level,
                component=component,
                session_id=session_id,
                metadata=metadata or {}
            )
            self.session.add(event)
            await self.session.commit()
            
        except Exception as e:
            # Only log non-session errors to avoid spam
            if "concurrent operations are not permitted" not in str(e):
                logger.error(f"Failed to log event: {e}")
            # Don't rollback for logging failures
    
    async def get_recent_events(self, limit: int = 100, level: Optional[str] = None) -> List[SystemEvent]:
        """Get recent system events."""
        try:
            query = select(SystemEvent).order_by(desc(SystemEvent.timestamp)).limit(limit)
            
            if level:
                query = query.where(SystemEvent.level == level)
            
            result = await self.session.execute(query)
            return result.scalars().all()
            
        except Exception as e:
            logger.error(f"Failed to get recent events: {e}")
            return []
    
    async def cleanup_old_events(self, days: int = 30) -> int:
        """Clean up old system events."""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            result = await self.session.execute(
                select(func.count(SystemEvent.id))
                .where(SystemEvent.timestamp < cutoff_date)
            )
            count = result.scalar()
            
            if count > 0:
                await self.session.execute(
                    select(SystemEvent).where(SystemEvent.timestamp < cutoff_date)
                )
                await self.session.commit()
                logger.info(f"Cleaned up {count} old events")
            
            return count
            
        except Exception as e:
            logger.error(f"Failed to cleanup old events: {e}")
            await self.session.rollback()
            return 0