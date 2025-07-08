"""
Web interface for Bedtime Storyteller.
Provides story library management, configuration, and real-time status.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends, Request, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
import uvicorn

from ..config.settings import get_settings
from ..storage.models import get_database_session, create_database_engine
from ..storage.story_library import StoryLibrary
from ..core.agent import StorytellingAgent
from ..providers.base import ProviderManager

logger = logging.getLogger(__name__)

# Pydantic models for API
class StoryRequest(BaseModel):
    """Request model for story generation."""
    prompt: str = Field(..., min_length=1, max_length=500)
    language: str = Field(default="tr", pattern="^(tr|en)$")
    age_rating: str = Field(default="5+", pattern="^[0-9]+\\+$")
    
class StoryResponse(BaseModel):
    """Response model for story generation."""
    session_id: str
    status: str
    message: str
    
class SessionInfo(BaseModel):
    """Session information model."""
    session_id: str
    prompt: str
    language: str
    age_rating: str
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    paragraphs_generated: int = 0
    
class SystemStatus(BaseModel):
    """System status model."""
    state: str
    is_running: bool
    current_session: Optional[SessionInfo] = None
    stats: Dict[str, Any] = Field(default_factory=dict)
    hardware_status: Dict[str, Any] = Field(default_factory=dict)
    provider_status: Dict[str, Any] = Field(default_factory=dict)

class WebApplication:
    """Main web application class."""
    
    def __init__(self):
        self.settings = get_settings()
        self.app = FastAPI(
            title="Bedtime Storyteller",
            description="AI-powered bedtime storytelling for children",
            version="0.1.0"
        )
        self.agent: Optional[StorytellingAgent] = None
        self.story_library: Optional[StoryLibrary] = None
        self.database_engine = None
        self.websocket_connections: List[WebSocket] = []
        
        # Setup templates and static files
        self.templates = Jinja2Templates(directory="storyteller/web/templates")
        
        # Create static directory if it doesn't exist
        static_dir = Path("storyteller/web/static")
        static_dir.mkdir(exist_ok=True)
        
        self.app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
        
        # Setup routes
        self._setup_routes()
        
        # Setup WebSocket for real-time updates
        self._setup_websocket()
    
    def _setup_routes(self):
        """Setup all web routes."""
        
        # Web interface routes
        @self.app.get("/", response_class=HTMLResponse)
        async def dashboard(request: Request):
            """Main dashboard page."""
            return self.templates.TemplateResponse("dashboard.html", {"request": request})
        
        @self.app.get("/stories", response_class=HTMLResponse)
        async def stories_page(request: Request):
            """Story library page."""
            return self.templates.TemplateResponse("stories.html", {"request": request})
        
        @self.app.get("/settings", response_class=HTMLResponse)
        async def settings_page(request: Request):
            """Settings page."""
            return self.templates.TemplateResponse("settings.html", {"request": request})
        
        # API routes
        @self.app.get("/api/status", response_model=SystemStatus)
        async def get_status():
            """Get current system status."""
            try:
                if not self.agent:
                    return SystemStatus(
                        state="offline",
                        is_running=False,
                        stats={"error": "Agent not initialized"}
                    )
                
                agent_status = self.agent.get_status()
                
                # Get hardware status
                hardware_status = {}
                if self.agent.hardware_manager:
                    hardware_status = await self.agent.hardware_manager.get_status()
                
                # Get provider status
                provider_status = {}
                if self.agent.provider_manager:
                    provider_status = await self.agent.provider_manager.health_check()
                
                return SystemStatus(
                    state=agent_status.get("state", "unknown"),
                    is_running=agent_status.get("is_running", False),
                    current_session=self._format_session_info(agent_status.get("current_session")),
                    stats=agent_status.get("stats", {}),
                    hardware_status=hardware_status,
                    provider_status=provider_status
                )
                
            except Exception as e:
                logger.error(f"Status check failed: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/stories", response_model=StoryResponse)
        async def create_story(request: StoryRequest):
            """Generate a new story."""
            try:
                if not self.agent:
                    raise HTTPException(status_code=503, detail="Agent not available")
                
                if not self.agent.state.value in ["idle", "listening"]:
                    raise HTTPException(status_code=409, detail="Agent is busy")
                
                # Start story generation
                session = await self.agent.tell_story(
                    request.prompt,
                    language=request.language,
                    age_rating=request.age_rating
                )
                
                # Notify WebSocket clients
                await self._broadcast_update({
                    "type": "story_started",
                    "session_id": session.session_id,
                    "prompt": request.prompt
                })
                
                return StoryResponse(
                    session_id=session.session_id,
                    status="started",
                    message="Story generation started"
                )
                
            except Exception as e:
                logger.error(f"Story creation failed: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/stories", response_model=List[SessionInfo])
        async def list_stories(limit: int = 20, offset: int = 0):
            """List recent stories."""
            try:
                if not self.story_library:
                    raise HTTPException(status_code=503, detail="Story library not available")
                
                sessions = await self.story_library.get_recent_sessions(limit=limit, offset=offset)
                
                return [
                    SessionInfo(
                        session_id=session.session_id,
                        prompt=session.prompt,
                        language=session.language,
                        age_rating=session.age_rating,
                        status=session.status,
                        created_at=session.created_at,
                        completed_at=session.completed_at,
                        paragraphs_generated=session.paragraphs_generated
                    )
                    for session in sessions
                ]
                
            except Exception as e:
                logger.error(f"Story listing failed: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/stories/{session_id}", response_model=SessionInfo)
        async def get_story(session_id: str):
            """Get specific story details."""
            try:
                if not self.story_library:
                    raise HTTPException(status_code=503, detail="Story library not available")
                
                session = await self.story_library.get_session(session_id)
                if not session:
                    raise HTTPException(status_code=404, detail="Story not found")
                
                return SessionInfo(
                    session_id=session.session_id,
                    prompt=session.prompt,
                    language=session.language,
                    age_rating=session.age_rating,
                    status=session.status,
                    created_at=session.created_at,
                    completed_at=session.completed_at,
                    paragraphs_generated=session.paragraphs_generated
                )
                
            except Exception as e:
                logger.error(f"Story retrieval failed: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.delete("/api/stories/{session_id}")
        async def delete_story(session_id: str):
            """Delete a story."""
            try:
                if not self.story_library:
                    raise HTTPException(status_code=503, detail="Story library not available")
                
                success = await self.story_library.delete_session(session_id)
                if not success:
                    raise HTTPException(status_code=404, detail="Story not found")
                
                return {"message": "Story deleted successfully"}
                
            except Exception as e:
                logger.error(f"Story deletion failed: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/wake")
        async def trigger_wake():
            """Manually trigger wake word detection."""
            try:
                if not self.agent:
                    raise HTTPException(status_code=503, detail="Agent not available")
                
                # Simulate wake word detection
                from ..wakeword.loader import WakewordDetection
                import time
                
                detection = WakewordDetection(
                    keyword="manual_trigger",
                    confidence=1.0,
                    timestamp=time.time(),
                    engine_name="web_interface"
                )
                
                self.agent._on_wake_word_detected(detection)
                
                return {"message": "Wake word triggered"}
                
            except Exception as e:
                logger.error(f"Wake trigger failed: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/settings")
        async def get_settings_api():
            """Get current settings."""
            try:
                settings = get_settings()
                return {
                    "wakeword_engine": settings.wakeword_engine,
                    "story_language": settings.story_language,
                    "story_age_rating": settings.story_age_rating,
                    "story_max_paragraphs": settings.story_max_paragraphs,
                    "max_memory_mb": settings.max_memory_mb,
                    "content_safety_enabled": settings.content_safety_enabled
                }
                
            except Exception as e:
                logger.error(f"Settings retrieval failed: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/settings")
        async def update_settings_api(settings_data: Dict[str, Any]):
            """Update settings."""
            try:
                # TODO: Implement settings update
                # This would require reloading the application with new settings
                return {"message": "Settings update not implemented yet"}
                
            except Exception as e:
                logger.error(f"Settings update failed: {e}")
                raise HTTPException(status_code=500, detail=str(e))
    
    def _setup_websocket(self):
        """Setup WebSocket for real-time updates."""
        
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket endpoint for real-time updates."""
            await websocket.accept()
            self.websocket_connections.append(websocket)
            
            try:
                while True:
                    # Keep connection alive
                    await websocket.receive_text()
                    
            except Exception as e:
                logger.debug(f"WebSocket connection closed: {e}")
            finally:
                if websocket in self.websocket_connections:
                    self.websocket_connections.remove(websocket)
    
    def _format_session_info(self, session_data: Optional[Dict[str, Any]]) -> Optional[SessionInfo]:
        """Format session data for API response."""
        if not session_data:
            return None
        
        return SessionInfo(
            session_id=session_data.get("session_id", ""),
            prompt=session_data.get("prompt", ""),
            language=session_data.get("language", "tr"),
            age_rating=session_data.get("age_rating", "5+"),
            status=session_data.get("status", "unknown"),
            created_at=session_data.get("created_at", datetime.now()),
            completed_at=session_data.get("completed_at"),
            paragraphs_generated=session_data.get("paragraphs_generated", 0)
        )
    
    async def _broadcast_update(self, message: Dict[str, Any]):
        """Broadcast update to all WebSocket connections."""
        if not self.websocket_connections:
            return
        
        disconnected = []
        for websocket in self.websocket_connections:
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.append(websocket)
        
        # Remove disconnected WebSocket connections
        for websocket in disconnected:
            self.websocket_connections.remove(websocket)
    
    async def initialize(self, agent: StorytellingAgent, story_library: StoryLibrary):
        """Initialize web application with agent and story library."""
        self.agent = agent
        self.story_library = story_library
        
        # Setup agent callbacks for WebSocket updates
        if self.agent:
            original_on_state_change = getattr(self.agent, 'on_state_change', None)
            original_on_story_started = getattr(self.agent, 'on_story_started', None)
            original_on_story_completed = getattr(self.agent, 'on_story_completed', None)
            
            async def on_state_change(new_state):
                await self._broadcast_update({
                    "type": "state_change",
                    "state": new_state.value
                })
                if original_on_state_change:
                    original_on_state_change(new_state)
            
            async def on_story_started(session):
                await self._broadcast_update({
                    "type": "story_started",
                    "session_id": session.session_id,
                    "prompt": session.prompt
                })
                if original_on_story_started:
                    original_on_story_started(session)
            
            async def on_story_completed(session):
                await self._broadcast_update({
                    "type": "story_completed",
                    "session_id": session.session_id,
                    "paragraphs_generated": session.paragraphs_generated
                })
                if original_on_story_completed:
                    original_on_story_completed(session)
            
            self.agent.on_state_change = on_state_change
            self.agent.on_story_started = on_story_started
            self.agent.on_story_completed = on_story_completed
        
        logger.info("Web application initialized")

# Global web application instance
web_app = WebApplication()

def create_app() -> FastAPI:
    """Create and return FastAPI application."""
    return web_app.app

def run_server(host: str = "0.0.0.0", port: int = 5000, **kwargs):
    """Run the web server."""
    uvicorn.run(
        "storyteller.web.app:create_app",
        host=host,
        port=port,
        factory=True,
        **kwargs
    )