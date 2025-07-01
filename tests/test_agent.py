"""
Standalone Test Agent for Invoice Processing AI MVP
Run this to test the agent functionality without modifying main.py
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional
import uvicorn
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app for testing
app = FastAPI(
    title="Invoice Processing AI - Test Agent",
    description="Standalone test agent for MVP demo",
    version="2.0.0-test"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models
class ChatMessage(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    success: bool
    session_id: str
    timestamp: str


class AgentStatus(BaseModel):
    status: str
    available_tools: list
    conversation_length: int
    uptime: str


# Simple conversation memory (in-memory for testing)
conversations = {}


class SimpleInvoiceAgent:
    """Simple rule-based agent for MVP demo"""

    def __init__(self):
        self.start_time = datetime.now()
        self.responses = {
            "greetings": [
                "hello", "hi", "hey", "good morning", "good afternoon",
                "good evening", "help", "assist"
            ],
            "process": [
                "process", "upload", "extract", "analyze document", "document ai"
            ],
            "search": [
                "search", "find", "lookup", "query", "show", "display", "list"
            ],
            "analytics": [
                "analytics", "insights", "patterns", "trends", "statistics",
                "analysis", "summary", "report"
            ],
            "examples": [
                "example", "demo", "sample", "test", "try"
            ]
        }

    def categorize_message(self, message: str) -> str:
        """Categorize user message to determine response type"""
        message_lower = message.lower()

        # Check for recent processing questions
        if any(word in message_lower for word in ["what did you", "just process", "recent", "latest", "last invoice"]):
            return "recent_processing"
        # Check for specific keywords
        elif any(word in message_lower for word in self.responses["process"]):
            return "process"
        elif any(word in message_lower for word in self.responses["search"]):
            return "search"
        elif any(word in message_lower for word in self.responses["analytics"]):
            return "analytics"
        elif any(word in message_lower for word in self.responses["examples"]):
            return "examples"
        elif any(word in message_lower for word in self.responses["greetings"]):
            return "greeting"
        else:
            return "general"

    # Add these methods to your SimpleInvoiceAgent class

    def get_recent_processing_data(self):
        """Get actual recent processing data from main API"""
        try:
            import json
            from pathlib import Path

            # Path to the recent processing file
            recent_file = Path(__file__).parent.parent / "recent_processing.json"

            if recent_file.exists():
                with open(recent_file, "r") as f:
                    data = json.load(f)

                # Check if data is recent (within last 10 minutes)
                from datetime import datetime, timedelta
                timestamp = datetime.fromisoformat(data["timestamp"].replace("Z", ""))
                if datetime.now() - timestamp < timedelta(minutes=10):
                    return data

            return None
        except Exception as e:
            print(f"Error reading recent processing data: {e}")
            return None

    def get_dynamic_recent_response(self):
        """Generate dynamic response based on actual recent processing"""
        recent_data = self.get_recent_processing_data()

        if recent_data:
            return f"""📊 **Recent Invoice Processing Results**

    I can see you just processed an invoice! Here are the actual details:

    **✅ Processing Complete:**
    - **File:** {recent_data['filename']}
    - **Vendor:** {recent_data['vendor']}
    - **Amount:** ${recent_data['amount']}
    - **Invoice #:** {recent_data['invoice_number']}
    - **Date:** {recent_data['invoice_date']}
    - **Processing Time:** {recent_data['processing_time']}
    - **Confidence:** {recent_data['confidence']}
    - **Line Items:** {recent_data['line_items_count']} items extracted

    **📋 My Analysis:**
    - ✅ **Vendor verification:** {recent_data['vendor']} details extracted successfully
    - ✅ **Amount validation:** ${recent_data['amount']} - {"appears reasonable" if float(recent_data['amount'].replace('$', '').replace(',', '')) < 5000 else "⚠️ High value - may need approval"}
    - ✅ **Processing quality:** {recent_data['confidence']} confidence - {"excellent" if "9" in recent_data['confidence'] else "good"} extraction
    - ✅ **Speed:** {recent_data['processing_time']} - high-performance processing

    **🔍 Business Insights:**
    - Invoice from **{recent_data['vendor']}** for **${recent_data['amount']}**
    - {"✅ Standard amount" if float(recent_data['amount'].replace('$', '').replace(',', '')) < 1000 else "⚠️ Review recommended - amount exceeds $1,000"}
    - {"✅ All data extracted" if recent_data['line_items_count'] > 0 else "ℹ️ Basic extraction completed"}
    - Processing completed in {recent_data['processing_time']} with {recent_data['confidence']} accuracy

    **💡 Recommendations:**
    - Verify vendor details match your approved vendor list
    - Check if amount aligns with any purchase orders
    - {"Set up approval workflow - amount exceeds typical thresholds" if float(recent_data['amount'].replace('$', '').replace(',', '')) > 2000 else "Standard processing workflow applies"}

    **Want specific analysis?** Ask me about vendor patterns, spending comparisons, or approval workflows!
    """
        else:
            return """📊 **Recent Invoice Processing Activity**

    I don't see any recent processing activity from the last 10 minutes. Here's how to get started:

    1. **Go to the Home page** and upload an invoice
    2. **Process the document** with our Document AI
    3. **Come back here within 10 minutes** and ask "What did you just process?"

    I'll then provide detailed analysis of your actual processing results with real data!

    **Recent activity expires after 10 minutes for security.**
    """

    def generate_response(self, message: str, session_id: str) -> Dict[str, Any]:
        """Generate response based on message category"""
        category = self.categorize_message(message)

        responses = {
            "greeting": """👋 Hello! I'm your Invoice Processing AI Assistant. I can help you:

        • 📄 **Process invoices** - Extract data from uploaded documents
        • 🔍 **Search invoices** - Find specific invoices by vendor, amount, date
        • 📊 **Analytics & insights** - Analyze spending patterns and trends
        • ⚠️ **Flag issues** - Detect duplicates, unusual amounts, missing data

        **Try asking:**
        - "How do I process an invoice?"
        - "Search for invoices from Microsoft"
        - "Show me spending analytics"
        - "What can you help me with?"
            """,

            "process": """📄 **Invoice Processing with Document AI**

        I can help you process invoices using Google Document AI! Here's how:

        **1. Upload Options:**
        - Use the `/process-invoice` endpoint
        - Supported formats: PDF, PNG, JPG, JPEG, TIFF, GIF
        - Maximum file size: 10MB

        **2. What I Extract:**
        - Vendor information and addresses
        - Invoice numbers and dates
        - Total amounts and line items
        - Tax information and due dates
        - Confidence scores for each field

        **3. Processing Time:**
        - Average: 3-9 seconds per document
        - 95%+ accuracy rate
        - Real-time confidence scoring

        **Want to try?** Upload an invoice file and I'll extract all the key information!
            """,

            "search": """🔍 **Invoice Search & Query Capabilities**

        I can help you find invoices using natural language! Here are examples:

        **By Vendor:**
        - "Find invoices from Acme Corp"
        - "Show me all Microsoft invoices"
        - "Invoices from suppliers in California"

        **By Amount:**
        - "Show invoices over $5,000"
        - "Find invoices between $1,000 and $10,000"
        - "Invoices under $500"

        **By Date:**
        - "Invoices from last month"
        - "Show Q1 2025 invoices"
        - "Invoices due this week"

        **Combined Queries:**
        - "Microsoft invoices over $2,000 from last quarter"
        - "Overdue invoices from top 5 vendors"

        *Note: Full search functionality requires database integration*
            """,

            "analytics": """📊 **Analytics & Business Insights**

        I provide comprehensive invoice analytics and insights:

        **Spending Analysis:**
        - Total spending by vendor, category, time period
        - Average invoice amounts and trends
        - Month-over-month comparison
        - Budget variance analysis

        **Vendor Insights:**
        - Top vendors by volume and amount
        - Payment term analysis
        - Duplicate vendor detection
        - Vendor performance metrics

        **Pattern Detection:**
        - Unusual invoice amounts (outliers)
        - Duplicate invoices
        - Missing purchase orders
        - Approval workflow bottlenecks

        **Automated Alerts:**
        - Invoices exceeding approval limits
        - Duplicate payments
        - Vendor payment terms violations
        - Budget threshold warnings

        **Want insights?** Ask me things like:
        - "What's my spending pattern this month?"
        - "Who are my top 5 vendors?"
        - "Flag anything unusual in recent invoices"
            """,

            "examples": """💡 **Demo Examples & Use Cases**

        Here are some realistic scenarios you can try:

        **1. Processing Workflow:**
        - Upload: "I have a new invoice to process"
        - Extract: "Process this PDF invoice from Acme Corp"
        - Validate: "Check if this invoice looks correct"

        **2. Search Examples:**
        - "Find all invoices from last month over $1,000"
        - "Show me Adobe subscription invoices"
        - "List invoices that need manager approval"

        **3. Analytics Queries:**
        - "What's my average monthly software spending?"
        - "Which vendors am I overpaying?"
        - "Show spending trends for office supplies"

        **4. Business Intelligence:**
        - "Flag duplicate invoices"
        - "Find invoices missing purchase orders"
        - "Which invoices are overdue for payment?"

        **Ready for a demo?** Try asking any of these questions!
            """,

            "recent_processing": self.get_dynamic_recent_response(),
            "general": f"""🤖 I understand you said: "{message}"

        I can see you're asking about recent processing! Based on your activity, here's what I can help you with:

        **Common Questions About Recent Processing:**
        - **"I just processed an invoice from [Vendor] for $[Amount]. What should I check?"**
        - **"Help me analyze the invoice I just uploaded"**
        - **"What insights can you provide about my recent processing?"**

        **What I can help you analyze:**
        - ✅ **Vendor Information** - Company details and addresses
        - ✅ **Financial Data** - Amounts, taxes, line items
        - ✅ **Processing Quality** - Confidence scores and accuracy
        - ✅ **Business Rules** - Flag unusual amounts or missing data
        - ✅ **Next Steps** - Approval workflows, payment processing

        **Example Analysis:**
        *"I just processed an Acme Corp invoice for $453.53"*

        → I can help you:
        - Verify the vendor details are correct
        - Check if the amount fits normal spending patterns  
        - Flag any missing purchase orders
        - Suggest approval workflows
        - Compare with previous Acme invoices

        **Want specific help?** Tell me about the invoice you just processed, and I'll provide targeted insights!
            """,

            "general": f"""🤖 I understand you said: "{message}"

        I'm your Invoice Processing AI Assistant, specialized in:

        • **Document Processing** - Extract data from invoice files
        • **Intelligent Search** - Find invoices using natural language
        • **Business Analytics** - Insights and spending patterns
        • **Workflow Automation** - Flag issues and streamline AP processes

        **Need help with something specific?** Try:
        - "Process this invoice"
        - "Search for vendor invoices"  
        - "Analyze my spending"
        - "Show me examples"

        What would you like me to help you with?
            """
        }
        return {
            "response": responses.get(category, responses["general"]),
            "success": True,
            "category": category,
            "message_length": len(message)
        }


# Initialize agent
agent = SimpleInvoiceAgent()


@app.get("/")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Invoice Processing AI - Test Agent",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0-test"
    }


@app.post("/agent/chat", response_model=ChatResponse)
async def chat_with_agent(chat_message: ChatMessage):
    """
    Chat with the Invoice Processing AI Agent
    """
    try:
        # Get or create session ID
        session_id = chat_message.session_id or f"test_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Store conversation in memory
        if session_id not in conversations:
            conversations[session_id] = []

        # Generate response
        agent_result = agent.generate_response(chat_message.message, session_id)

        # Store conversation
        conversations[session_id].append({
            "timestamp": datetime.now().isoformat(),
            "user_message": chat_message.message,
            "agent_response": agent_result["response"],
            "category": agent_result.get("category", "unknown")
        })

        return ChatResponse(
            response=agent_result["response"],
            success=agent_result["success"],
            session_id=session_id,
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Agent error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")


@app.get("/agent/status", response_model=AgentStatus)
async def get_agent_status():
    """Get current agent status and capabilities"""
    uptime = datetime.now() - agent.start_time

    return AgentStatus(
        status="ready",
        available_tools=[
            "invoice_processing",
            "document_search",
            "analytics_insights",
            "business_intelligence",
            "workflow_automation"
        ],
        conversation_length=sum(len(conv) for conv in conversations.values()),
        uptime=str(uptime).split('.')[0]  # Remove microseconds
    )


@app.get("/agent/conversations")
async def get_conversations():
    """Get all conversation history (for testing)"""
    return {
        "total_sessions": len(conversations),
        "total_messages": sum(len(conv) for conv in conversations.values()),
        "conversations": conversations
    }


@app.post("/agent/clear")
async def clear_conversations():
    """Clear all conversation history"""
    global conversations
    conversations = {}
    return {"message": "All conversations cleared", "timestamp": datetime.now().isoformat()}


@app.get("/agent/demo")
async def demo_scenarios():
    """Get demo scenarios for testing"""
    return {
        "demo_scenarios": [
            {
                "category": "greeting",
                "input": "Hello, can you help me with invoices?",
                "description": "Basic greeting and introduction"
            },
            {
                "category": "process",
                "input": "How do I process an invoice?",
                "description": "Invoice processing workflow"
            },
            {
                "category": "search",
                "input": "Find invoices from Microsoft over $1000",
                "description": "Complex search query"
            },
            {
                "category": "analytics",
                "input": "What insights can you provide about my spending?",
                "description": "Analytics and business intelligence"
            },
            {
                "category": "examples",
                "input": "Show me some examples of what you can do",
                "description": "Demo examples and use cases"
            }
        ]
    }


# Run the test agent
if __name__ == "__main__":
    logger.info("🚀 Starting Invoice Processing AI Test Agent...")
    logger.info("📍 Access at: http://localhost:8001")
    logger.info("📖 API docs at: http://localhost:8001/docs")

    uvicorn.run(
        "test_agent:app",
        host="0.0.0.0",
        port=8001,  # Different port from main app
        reload=True,
        log_level="info"
    )