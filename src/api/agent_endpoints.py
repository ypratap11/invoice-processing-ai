from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from src.agents.invoice_agent import get_agent
from src.database import create_tables, get_db
from sqlalchemy.orm import Session
import uuid

# Create router for agent endpoints
agent_router = APIRouter(prefix="/agent", tags=["AI Agent"])

# Initialize database tables
create_tables()


class ChatMessage(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    success: bool
    session_id: str
    tools_used: Optional[List[str]] = []
    intermediate_steps: Optional[List[Any]] = []


class AgentStatus(BaseModel):
    status: str
    available_tools: List[str]
    conversation_length: int


@agent_router.post("/chat", response_model=ChatResponse)
async def chat_with_agent(
        chat_message: ChatMessage,
        db: Session = Depends(get_db)
):
    """
    Chat with the Invoice Processing AI Agent

    The agent can:
    - Process invoices using Document AI
    - Search historical invoice data
    - Provide analytics and insights
    - Answer questions about spending patterns
    """
    try:
        # Get or create session ID
        session_id = chat_message.session_id or str(uuid.uuid4())

        # Get agent instance
        agent = get_agent()

        # Process the message
        result = agent.process_message(
            message=chat_message.message,
            session_id=session_id
        )

        # TODO: Save conversation to database
        # save_conversation_to_db(chat_message.message, result["response"], session_id, db)

        return ChatResponse(
            response=result["response"],
            success=result["success"],
            session_id=session_id,
            tools_used=result.get("tools_used", []),
            intermediate_steps=result.get("intermediate_steps", [])
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")


@agent_router.get("/status", response_model=AgentStatus)
async def get_agent_status():
    """Get current agent status and capabilities"""
    try:
        agent = get_agent()

        return AgentStatus(
            status="ready",
            available_tools=[tool.name for tool in agent.tools],
            conversation_length=len(agent.get_conversation_history())
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Status error: {str(e)}")


@agent_router.post("/clear-conversation")
async def clear_conversation():
    """Clear the current conversation history"""
    try:
        agent = get_agent()
        agent.clear_conversation()

        return {"message": "Conversation history cleared successfully"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clear error: {str(e)}")


@agent_router.get("/commands")
async def get_available_commands():
    """Get list of available commands and examples"""
    try:
        agent = get_agent()
        commands = agent.get_available_commands()

        return {
            "commands": commands,
            "examples": [
                "Process this invoice",
                "Show me invoices from Microsoft",
                "Find invoices over $5000",
                "Analyze my spending this quarter",
                "What patterns do you see in my invoices?"
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Commands error: {str(e)}")


# Demo endpoints for testing
@agent_router.post("/demo/test-scenarios")
async def test_demo_scenarios():
    """Test agent with predefined demo scenarios"""
    from src.agents.invoice_agent import DEMO_SCENARIOS

    try:
        agent = get_agent()
        results = []

        for scenario in DEMO_SCENARIOS:
            result = agent.process_message(scenario["user_input"])
            results.append({
                "scenario": scenario["description"],
                "input": scenario["user_input"],
                "output": result["response"],
                "success": result["success"],
                "tools_used": result.get("tools_used", [])
            })

        return {"demo_results": results}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Demo error: {str(e)}")


# Health check for agent
@agent_router.get("/health")
async def agent_health_check():
    """Check if the agent is working properly"""
    try:
        agent = get_agent()

        # Test with a simple message
        test_result = agent.process_message("Hello, are you working?")

        return {
            "status": "healthy" if test_result["success"] else "unhealthy",
            "agent_response": test_result["response"],
            "tools_available": len(agent.tools),
            "memory_working": len(agent.get_conversation_history()) >= 0
        }

    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


# Integration instructions for your existing main.py
"""
To integrate this with your existing FastAPI app, add these lines to your main.py:

from src.api.agent_endpoints import agent_router

# Add this line after creating your FastAPI app instance
app.include_router(agent_router)

# Your existing endpoints will continue to work unchanged
"""