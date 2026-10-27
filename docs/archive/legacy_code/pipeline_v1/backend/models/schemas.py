from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class ResearchStreamRequest(BaseModel):
    topic: str = Field(default="Autonomous Research Topic", description="Target research objective")
    mode: str = Field(default="auto", description="Execution mode: auto, fast_chat, deep_research")
    role: str = Field(default="senior academic researcher", description="Persona role")
    tone: str = Field(default="formal and analytical", description="Persona tone")
    scrape_top_n: int = Field(default=15, ge=1, le=50, description="Paper scrape count")
    min_score: float = Field(default=6.5, ge=0.0, le=10.0, description="Critic pass threshold")
    chat_turns: List[Dict[str, Any]] = Field(default_factory=list, description="Prior conversation context")
    conversation_summary: str = Field(default="", description="Rolling summary")

class FollowupStreamRequest(BaseModel):
    state: Optional[Dict[str, Any]] = Field(default=None, description="Previous research state")
    user_query: str = Field(..., description="Follow-up question or modification")
    mode_override: Optional[str] = Field(default=None, description="Explicit mode override")

class BrainstormMatchRequest(BaseModel):
    query: str = Field(..., description="User philosophical inquiry or problem")
    chat_turns: List[Dict[str, Any]] = Field(default_factory=list, description="Prior brainstorming turns")

class BrainstormChatRequest(BaseModel):
    thinker_id: str = Field(default="auto", description="Target philosopher ID or auto")
    message: str = Field(..., description="Message for intellectual sparring")
    chat_turns: List[Dict[str, Any]] = Field(default_factory=list, description="Prior sparring dialogue")

class HealthResponse(BaseModel):
    status: str = "healthy"
    service: str = "thoth-backend"
    version: str = "3.0.0"
    timestamp: str

class ReadyResponse(BaseModel):
    status: str
    database: str
    redis: str
    timestamp: str
