from langchain_google_vertexai import ChatVertexAI
from langchain.agents import create_openai_functions_agent, AgentExecutor
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationBufferMemory
from langchain.schema.messages import SystemMessage
from src.agents.tools import AVAILABLE_TOOLS
import os
from typing import Dict, Any


class InvoiceAgent:
    def __init__(self):
        """Initialize the Invoice Processing AI Agent"""

        # Initialize Vertex AI LLM
        self.llm = ChatVertexAI(
            model_name="gemini-pro",
            project=os.getenv("GCP_PROJECT_ID", "your-project-id"),
            location=os.getenv("GCP_LOCATION", "us-central1"),
            temperature=0.1  # Low temperature for consistent business responses
        )

        # Available tools
        self.tools = AVAILABLE_TOOLS

        # Create memory for conversation history
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
            output_key="output"
        )

        # Create agent prompt template
        self.prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=self._get_system_prompt()),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])

        # Create the agent
        self.agent = create_openai_functions_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=self.prompt
        )

        # Create agent executor
        self.executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            memory=self.memory,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=3,
            return_intermediate_steps=True
        )

    def _get_system_prompt(self) -> str:
        """System prompt defining the agent's behavior"""
        return """You are an AI-powered Invoice Processing Assistant. You help businesses automate their accounts payable workflows with intelligence and efficiency.

**Your Capabilities:**
- Process invoice documents using Google Document AI
- Search and analyze historical invoice data
- Provide business insights and spending analytics
- Flag unusual patterns or potential issues
- Remember conversation context for follow-up questions

**Your Personality:**
- Professional but friendly
- Precise with financial data
- Proactive in suggesting insights
- Concise but thorough in responses

**Business Rules:**
- Always confirm invoice details before processing
- Flag invoices over $3,000 for management approval
- Highlight duplicate vendors or unusual patterns
- Provide confidence scores for extractions
- Maintain data accuracy and security

**Response Format:**
- Use clear formatting with emojis for visual appeal
- Provide specific numbers and dates
- Include actionable insights when relevant
- Keep responses concise but informative

Remember: You're here to save time, reduce errors, and provide valuable business insights from invoice data."""

    def process_message(self, message: str, session_id: str = "default") -> Dict[str, Any]:
        """Process a user message and return agent response"""
        try:
            # Invoke the agent
            result = self.executor.invoke({
                "input": message,
                "session_id": session_id
            })

            return {
                "success": True,
                "response": result["output"],
                "intermediate_steps": result.get("intermediate_steps", []),
                "tools_used": [step[0].tool for step in result.get("intermediate_steps", [])]
            }

        except Exception as e:
            return {
                "success": False,
                "response": f"❌ I encountered an error processing your request: {str(e)}",
                "error": str(e)
            }

    def get_conversation_history(self) -> list:
        """Get the current conversation history"""
        if hasattr(self.memory, 'chat_memory'):
            return self.memory.chat_memory.messages
        return []

    def clear_conversation(self):
        """Clear the conversation history"""
        self.memory.clear()

    def get_available_commands(self) -> list:
        """Get list of available commands for the user"""
        return [
            "Process this invoice - Upload and extract data from invoice files",
            "Search invoices from [vendor] - Find invoices by vendor name",
            "Show invoices over $[amount] - Find invoices above a certain amount",
            "Analyze spending this month - Get analytics and insights",
            "What should I flag? - Get recommendations for review",
            "Show recent invoices - Display recently processed invoices"
        ]


# Global agent instance
_agent_instance = None


def get_agent() -> InvoiceAgent:
    """Get or create the global agent instance"""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = InvoiceAgent()
    return _agent_instance


# Demo scenarios for testing
DEMO_SCENARIOS = [
    {
        "user_input": "Process the uploaded invoice",
        "expected_tools": ["process_invoice"],
        "description": "Basic invoice processing"
    },
    {
        "user_input": "Show me all invoices from Acme Corp",
        "expected_tools": ["search_invoices"],
        "description": "Vendor search"
    },
    {
        "user_input": "What's my spending pattern this month?",
        "expected_tools": ["analyze_invoices"],
        "description": "Analytics and insights"
    },
    {
        "user_input": "Find invoices over $2000",
        "expected_tools": ["search_invoices"],
        "description": "Amount-based search"
    }
]