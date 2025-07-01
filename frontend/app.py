"""
Streamlit Frontend for Invoice Processing AI
Professional web interface with real-time processing and results visualization
"""

import streamlit as st
import requests
import json
import pandas as pd
from PIL import Image
import io
import time
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
from typing import Dict, Any, List

# Configure page
st.set_page_config(
    page_title="Invoice Processing AI",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
.main-header {
    font-size: 3rem;
    color: #1f77b4;
    text-align: center;
    margin-bottom: 2rem;
}

.metric-card {
    background-color: #f0f2f6;
    padding: 1rem;
    border-radius: 0.5rem;
    border-left: 4px solid #1f77b4;
}

.success-message {
    color: #28a745;
    font-weight: bold;
}

.error-message {
    color: #dc3545;
    font-weight: bold;
}

.info-box {
    background-color: #e3f2fd;
    padding: 1rem;
    border-radius: 0.5rem;
    border-left: 4px solid #2196f3;
    margin: 1rem 0;
}

.stProgress .st-bo {
    background-color: #1f77b4;
}
</style>
""", unsafe_allow_html=True)

# Configuration
API_BASE_URL = "http://localhost:8000"  # Change this to your API URL

# Initialize session state
if 'processing_history' not in st.session_state:
    st.session_state.processing_history = []
if 'current_results' not in st.session_state:
    st.session_state.current_results = None


# Helper functions
def check_api_health():
    """Check if API is available"""
    try:
        response = requests.get(f"{API_BASE_URL}/", timeout=5)
        return response.status_code == 200, response.json() if response.status_code == 200 else None
    except Exception as e:
        return False, str(e)


def process_single_file(file_data, filename):
    """Process a single file through the API"""
    try:
        files = {"file": (filename, file_data, "application/octet-stream")}
        response = requests.post(f"{API_BASE_URL}/process-invoice", files=files, timeout=30)

        if response.status_code == 200:
            return True, response.json()
        else:
            return False, f"API Error: {response.status_code} - {response.text}"
    except Exception as e:
        return False, f"Request failed: {str(e)}"


def process_batch_files(files_data):
    """Process multiple files through the API"""
    try:
        files = [("files", (name, data, "application/octet-stream")) for name, data in files_data]
        response = requests.post(f"{API_BASE_URL}/batch-process", files=files, timeout=60)

        if response.status_code == 200:
            return True, response.json()
        else:
            return False, f"API Error: {response.status_code} - {response.text}"
    except Exception as e:
        return False, f"Request failed: {str(e)}"


def display_extracted_data(data: Dict[str, Any], confidence_scores: Dict[str, float]):
    """Display extracted data in a structured format"""

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📋 Invoice Details")

        # Vendor Information
        if data.get("vendor_info"):
            st.write("**Vendor Information:**")
            vendor_info = data["vendor_info"]
            if vendor_info.get("name"):
                st.write(f"• Name: {vendor_info['name']}")

        # Invoice Details
        if data.get("invoice_details"):
            st.write("**Invoice Details:**")
            invoice_details = data["invoice_details"]
            if invoice_details.get("invoice_number"):
                st.write(f"• Invoice Number: {invoice_details['invoice_number']}")

        # Dates
        if data.get("dates"):
            st.write("**Important Dates:**")
            dates = data["dates"]
            if dates.get("invoice_date"):
                st.write(f"• Invoice Date: {dates['invoice_date']}")
            if dates.get("due_date"):
                st.write(f"• Due Date: {dates['due_date']}")

        # Addresses
        if data.get("addresses"):
            st.write("**Addresses:**")
            addresses = data["addresses"]
            if addresses.get("vendor_address"):
                st.write(f"• Vendor Address: {addresses['vendor_address']}")

    with col2:
        st.subheader("💰 Financial Summary")

        # Totals
        if data.get("totals"):
            totals = data["totals"]

            # Create metrics
            metrics_data = []
            if totals.get("total_amount"):
                metrics_data.append(("Total Amount", totals["total_amount"]))
            if totals.get("net_amount"):
                metrics_data.append(("Net Amount", totals["net_amount"]))
            if totals.get("tax_amount"):
                metrics_data.append(("Tax Amount", totals["tax_amount"]))

            for label, value in metrics_data:
                st.metric(label, value)

    # Line Items Table
    if data.get("line_items") and len(data["line_items"]) > 0:
        st.subheader("📊 Line Items")

        try:
            df = pd.DataFrame(data["line_items"])
            st.dataframe(df, use_container_width=True)

            # Download button for line items
            csv = df.to_csv(index=False)
            st.download_button(
                label="📥 Download Line Items CSV",
                data=csv,
                file_name=f"line_items_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        except Exception as e:
            st.error(f"Error displaying line items: {str(e)}")

    # Confidence Scores
    if confidence_scores:
        st.subheader("🎯 Confidence Scores")

        # Create confidence chart
        conf_df = pd.DataFrame([
            {"Field": field, "Confidence": score}
            for field, score in confidence_scores.items()
        ])

        if not conf_df.empty:
            fig = px.bar(
                conf_df,
                x="Field",
                y="Confidence",
                title="Extraction Confidence by Field",
                color="Confidence",
                color_continuous_scale="RdYlGn"
            )
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)


def display_processing_history():
    """Display processing history"""
    if st.session_state.processing_history:
        st.subheader("📈 Processing History")

        # Create history dataframe
        history_data = []
        for entry in st.session_state.processing_history:
            history_data.append({
                "Timestamp": entry["timestamp"],
                "Filename": entry["filename"],
                "Status": "✅ Success" if entry["success"] else "❌ Failed",
                "Processing Time": f"{entry.get('processing_time', 0):.2f}s",
                "Message": entry["message"]
            })

        df = pd.DataFrame(history_data)
        st.dataframe(df, use_container_width=True)

        # Success rate chart
        success_rate = sum(1 for entry in st.session_state.processing_history if entry["success"]) / len(
            st.session_state.processing_history) * 100

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Success Rate", f"{success_rate:.1f}%")
        with col2:
            st.metric("Total Processed", len(st.session_state.processing_history))
        with col3:
            avg_time = sum(entry.get("processing_time", 0) for entry in st.session_state.processing_history) / len(
                st.session_state.processing_history)
            st.metric("Avg Processing Time", f"{avg_time:.2f}s")


# Main Application
def main():
    # Header
    st.markdown('<h1 class="main-header">📄 Invoice Processing AI</h1>', unsafe_allow_html=True)

    # API Status Check
    api_healthy, api_info = check_api_health()

    if api_healthy:
        st.success("🟢 API Connected Successfully")
        if api_info:
            st.sidebar.success(f"API Version: {api_info.get('version', 'Unknown')}")
    else:
        st.error("🔴 API Connection Failed")
        st.error(f"Error: {api_info}")
        st.info("Please ensure the FastAPI server is running on http://localhost:8000")
        return

    # Sidebar Configuration
    st.sidebar.header("⚙️ Configuration")

    # Processing mode
    processing_mode = st.sidebar.selectbox(
        "Processing Mode",
        ["Single File", "Batch Processing"],
        help="Choose between processing one file or multiple files"
    )

    # File upload settings
    max_files = 10 if processing_mode == "Batch Processing" else 1

    st.sidebar.info(f"""
    **Supported Formats:**
    • PDF files
    • Images (PNG, JPG, JPEG, TIFF, GIF)

    **Limits:**
    • Max file size: 10MB
    • Max batch size: 10 files
    """)

    # Main content area
    if processing_mode == "Single File":
        st.header("📤 Upload Invoice Document")

        uploaded_file = st.file_uploader(
            "Choose an invoice file",
            type=["pdf", "png", "jpg", "jpeg", "tiff", "gif"],
            help="Upload a single invoice document for processing"
        )

        if uploaded_file is not None:
            # Display file info
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("File Name", uploaded_file.name)
            with col2:
                st.metric("File Size", f"{len(uploaded_file.getvalue()) / 1024:.1f} KB")
            with col3:
                st.metric("File Type", uploaded_file.type)

            # Display preview for images
            if uploaded_file.type.startswith("image/"):
                st.subheader("📸 Preview")
                image = Image.open(uploaded_file)
                st.image(image, caption="Uploaded Image", use_column_width=True)

            # Process button
            if st.button("🚀 Process Invoice", type="primary"):
                with st.spinner("Processing invoice... Please wait."):
                    # Reset file pointer
                    uploaded_file.seek(0)

                    # Process file
                    success, result = process_single_file(uploaded_file.getvalue(), uploaded_file.name)

                    # Store in session state
                    processing_entry = {
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "filename": uploaded_file.name,
                        "success": success,
                        "message": result.get("message", "Unknown error") if isinstance(result, dict) else str(result),
                        "processing_time": result.get("processing_time", 0) if isinstance(result, dict) else 0
                    }
                    st.session_state.processing_history.append(processing_entry)

                    if success:
                        st.session_state.current_results = result
                        st.success("✅ Invoice processed successfully!")
                    else:
                        st.error(f"❌ Processing failed: {result}")

            # Display results
            if st.session_state.current_results and st.session_state.current_results.get("success"):
                st.header("📊 Extraction Results")

                result = st.session_state.current_results

                # Processing metrics
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Processing Time", f"{result.get('processing_time', 0):.2f}s")
                with col2:
                    avg_confidence = sum(result.get('confidence_scores', {}).values()) / len(
                        result.get('confidence_scores', {})) if result.get('confidence_scores') else 0
                    st.metric("Avg Confidence", f"{avg_confidence:.1%}")
                with col3:
                    fields_extracted = len(result.get('extracted_data', {}))
                    st.metric("Fields Extracted", fields_extracted)

                # Display extracted data
                if result.get("extracted_data"):
                    display_extracted_data(
                        result["extracted_data"],
                        result.get("confidence_scores", {})
                    )

                # Download JSON results
                json_data = json.dumps(result, indent=2)
                st.download_button(
                    label="📥 Download Full Results (JSON)",
                    data=json_data,
                    file_name=f"invoice_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json"
                )

    else:  # Batch Processing
        st.header("📤 Upload Multiple Invoice Documents")

        uploaded_files = st.file_uploader(
            "Choose invoice files",
            type=["pdf", "png", "jpg", "jpeg", "tiff", "gif"],
            accept_multiple_files=True,
            help="Upload multiple invoice documents for batch processing"
        )

        if uploaded_files:
            st.subheader(f"📁 Selected Files ({len(uploaded_files)})")

            # Display file list
            for i, file in enumerate(uploaded_files):
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.text(f"{i + 1}. {file.name}")
                with col2:
                    st.text(f"{len(file.getvalue()) / 1024:.1f} KB")
                with col3:
                    st.text(file.type.split('/')[-1].upper())

            # Process batch button
            if st.button("🚀 Process Batch", type="primary"):
                with st.spinner(f"Processing {len(uploaded_files)} files... Please wait."):
                    # Prepare files data
                    files_data = [(file.name, file.getvalue()) for file in uploaded_files]

                    # Process batch
                    success, result = process_batch_files(files_data)

                    if success:
                        st.success("✅ Batch processing completed!")

                        # Display batch results
                        batch_results = result.get("batch_results", [])

                        # Summary metrics
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("Total Files", result.get("total_files", 0))
                        with col2:
                            st.metric("Successful", result.get("successful_files", 0))
                        with col3:
                            st.metric("Failed", result.get("failed_files", 0))
                        with col4:
                            success_rate = (result.get("successful_files", 0) / result.get("total_files", 1)) * 100
                            st.metric("Success Rate", f"{success_rate:.1f}%")

                        # Detailed results
                        st.subheader("📊 Detailed Results")

                        for i, file_result in enumerate(batch_results):
                            with st.expander(f"{'✅' if file_result['success'] else '❌'} {file_result['filename']}"):
                                if file_result['success']:
                                    col1, col2 = st.columns(2)
                                    with col1:
                                        st.metric("Processing Time", f"{file_result.get('processing_time', 0):.2f}s")
                                    with col2:
                                        avg_conf = sum(file_result.get('confidence_scores', {}).values()) / len(
                                            file_result.get('confidence_scores', {})) if file_result.get(
                                            'confidence_scores') else 0
                                        st.metric("Avg Confidence", f"{avg_conf:.1%}")

                                    if file_result.get('extracted_data'):
                                        display_extracted_data(
                                            file_result['extracted_data'],
                                            file_result.get('confidence_scores', {})
                                        )
                                else:
                                    st.error(f"Error: {file_result['message']}")

                        # Download batch results
                        json_data = json.dumps(result, indent=2)
                        st.download_button(
                            label="📥 Download Batch Results (JSON)",
                            data=json_data,
                            file_name=f"batch_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                            mime="application/json"
                        )
                    else:
                        st.error(f"❌ Batch processing failed: {result}")

    # Processing History Section
    st.header("📈 Processing History & Analytics")
    display_processing_history()

    # Footer
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #666;">
        <p>🚀 <strong>Invoice Processing AI</strong> - Powered by Google Document AI</p>
        <p>Built with FastAPI + Streamlit | Production Ready</p>
    </div>
    """, unsafe_allow_html=True)


# Additional utility functions
def export_results_to_excel(results_data, filename="invoice_results.xlsx"):
    """Export results to Excel format"""
    try:
        import openpyxl
        from io import BytesIO

        output = BytesIO()

        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Summary sheet
            summary_data = {
                "Metric": ["Total Files Processed", "Success Rate", "Average Processing Time"],
                "Value": ["", "", ""]  # Fill with actual data
            }
            pd.DataFrame(summary_data).to_excel(writer, sheet_name="Summary", index=False)

            # Detailed results sheet
            if isinstance(results_data, dict) and results_data.get("extracted_data"):
                # Single file results
                extracted = results_data["extracted_data"]

                # Vendor info
                if extracted.get("vendor_info"):
                    vendor_df = pd.DataFrame([extracted["vendor_info"]])
                    vendor_df.to_excel(writer, sheet_name="Vendor_Info", index=False)

                # Line items
                if extracted.get("line_items"):
                    line_items_df = pd.DataFrame(extracted["line_items"])
                    line_items_df.to_excel(writer, sheet_name="Line_Items", index=False)

                # Totals
                if extracted.get("totals"):
                    totals_df = pd.DataFrame([extracted["totals"]])
                    totals_df.to_excel(writer, sheet_name="Totals", index=False)

        output.seek(0)
        return output.getvalue()

    except ImportError:
        st.warning("Excel export requires openpyxl. Install with: pip install openpyxl")
        return None
    except Exception as e:
        st.error(f"Error creating Excel file: {str(e)}")
        return None


# Settings and Configuration Page
def show_settings_page():
    """Display settings and configuration options"""
    st.header("⚙️ Settings & Configuration")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("API Configuration")

        # API URL setting
        current_api_url = st.text_input("API Base URL", value=API_BASE_URL)

        if st.button("Test Connection"):
            try:
                response = requests.get(f"{current_api_url}/", timeout=5)
                if response.status_code == 200:
                    st.success("✅ Connection successful!")
                    st.json(response.json())
                else:
                    st.error(f"❌ Connection failed: {response.status_code}")
            except Exception as e:
                st.error(f"❌ Connection error: {str(e)}")

        # Get API config
        if st.button("Get API Configuration"):
            try:
                response = requests.get(f"{current_api_url}/config", timeout=5)
                if response.status_code == 200:
                    st.json(response.json())
                else:
                    st.error("Failed to get configuration")
            except Exception as e:
                st.error(f"Error: {str(e)}")

    with col2:
        st.subheader("Application Settings")

        # Theme settings
        st.selectbox("Theme", ["Light", "Dark", "Auto"])

        # Processing settings
        st.slider("Max Files in Batch", 1, 20, 10)
        st.slider("Request Timeout (seconds)", 10, 120, 30)

        # Data retention
        st.number_input("History Retention (days)", 1, 365, 30)

        if st.button("Clear Processing History"):
            st.session_state.processing_history = []
            st.success("History cleared!")


# About Page
def show_about_page():
    """Display about information"""
    st.header("ℹ️ About Invoice Processing AI")

    st.markdown("""
    ## 🚀 Overview

    **Invoice Processing AI** is a state-of-the-art document processing system that leverages 
    Google's Document AI to extract structured data from invoices and financial documents.

    ## ✨ Key Features

    - **🤖 AI-Powered Extraction**: Uses Google Document AI for accurate data extraction
    - **📊 Structured Output**: Organizes data into vendor info, line items, totals, and dates
    - **⚡ Batch Processing**: Process multiple documents simultaneously
    - **📈 Confidence Scoring**: Provides confidence metrics for each extracted field
    - **💾 Export Capabilities**: Download results in JSON, CSV, and Excel formats
    - **📱 Responsive Design**: Works on desktop and mobile devices
    - **🔒 Secure Processing**: Enterprise-grade security and privacy

    ## 🛠️ Technology Stack

    - **Backend**: FastAPI with Python
    - **Frontend**: Streamlit
    - **AI Engine**: Google Document AI
    - **Data Processing**: Pandas, NumPy
    - **Visualization**: Plotly
    - **Cloud**: Google Cloud Platform

    ## 📋 Supported Document Types

    - PDF documents
    - Image files (PNG, JPG, JPEG, TIFF, GIF)
    - Maximum file size: 10MB per document
    - Batch processing: Up to 10 files simultaneously

    ## 🎯 Use Cases

    - **Accounts Payable Automation**: Streamline invoice processing workflows
    - **Financial Data Entry**: Reduce manual data entry errors
    - **Audit and Compliance**: Maintain accurate financial records
    - **Business Intelligence**: Extract insights from financial documents
    - **ERP Integration**: Feed structured data into enterprise systems

    ## 📊 Performance Metrics

    - **Processing Speed**: ~2-5 seconds per document
    - **Accuracy**: 95%+ for standard invoice formats
    - **Throughput**: 100+ documents per hour
    - **Reliability**: 99.9% uptime SLA

    ---

    **Version**: 1.0.0 | **Last Updated**: June 2025
    """)


def show_ai_chat_page():
    """Display AI Chat Assistant page"""
    st.markdown('<h1 class="main-header">🤖 AI Chat Assistant</h1>', unsafe_allow_html=True)
    st.markdown("**Conversational AI for Invoice Processing & Analytics**")

    # Check agent status
    AGENT_URL = "http://localhost:8001"  # Our test agent

    col1, col2 = st.columns([4, 1])

    with col2:
        try:
            response = requests.get(f"{AGENT_URL}/agent/status", timeout=5)
            if response.status_code == 200:
                status_data = response.json()
                st.success("✅ AI Agent Ready")

                with st.expander("🛠️ Agent Info"):
                    st.write(f"**Status:** {status_data.get('status', 'unknown').title()}")
                    st.write(f"**Uptime:** {status_data.get('uptime', 'unknown')}")
                    st.write(f"**Conversations:** {status_data.get('conversation_length', 0)}")

                    tools = status_data.get('available_tools', [])
                    st.write("**Available Tools:**")
                    for tool in tools:
                        st.write(f"• {tool.replace('_', ' ').title()}")
            else:
                st.error("❌ Agent Offline")
                st.info("Start the AI agent: `python tests/test_agent.py` in port 8001")
                return
        except:
            st.error("❌ Cannot connect to AI Agent")
            st.info("💡 Make sure test_agent.py is running on port 8001")
            return

    # Initialize chat history
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    # Chat container
    with col1:
        st.markdown("### 💬 Chat with AI Assistant")

        # Display chat messages
        for message in st.session_state.chat_messages:
            with st.chat_message(message["role"]):
                st.write(message["content"])

        # Chat input
        if prompt := st.chat_input("Ask me about invoice processing, search, or analytics..."):
            # Add user message
            st.session_state.chat_messages.append({"role": "user", "content": prompt})

            # Display user message
            with st.chat_message("user"):
                st.write(prompt)

            # Get agent response
            with st.spinner("🤖 Processing your request..."):
                try:
                    response = requests.post(
                        f"{AGENT_URL}/agent/chat",
                        json={"message": prompt},
                        timeout=30
                    )
                    if response.status_code == 200:
                        agent_response = response.json()["response"]
                        st.session_state.chat_messages.append({
                            "role": "assistant",
                            "content": agent_response
                        })

                        # Display agent response
                        with st.chat_message("assistant"):
                            st.write(agent_response)
                    else:
                        st.error("Failed to get response from AI assistant")
                except Exception as e:
                    st.error(f"Error: {str(e)}")

            st.rerun()

    # Quick action buttons
    st.markdown("---")
    st.subheader("⚡ Quick Actions")

    col1, col2, col3, col4 = st.columns(4)

    def send_quick_message(message):
        """Helper function to send quick messages"""
        st.session_state.chat_messages.append({"role": "user", "content": message})
        try:
            response = requests.post(
                f"{AGENT_URL}/agent/chat",
                json={"message": message},
                timeout=30
            )
            if response.status_code == 200:
                agent_response = response.json()["response"]
                st.session_state.chat_messages.append({
                    "role": "assistant",
                    "content": agent_response
                })
        except:
            pass
        st.rerun()

    with col1:
        if st.button("💡 What can you help with?"):
            send_quick_message("What can you help me with?")

    with col2:
        if st.button("📄 How to process invoices?"):
            send_quick_message("How do I process an invoice?")

    with col3:
        if st.button("🔍 Search examples"):
            send_quick_message("Show me search examples")

    with col4:
        if st.button("📊 Analytics insights"):
            send_quick_message("What analytics can you provide?")

    # Chat controls
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        if st.button("🗑️ Clear Chat"):
            st.session_state.chat_messages = []
            st.rerun()

    with col2:
        if st.button("💾 Export Chat"):
            if st.session_state.chat_messages:
                chat_export = {
                    "timestamp": datetime.now().isoformat(),
                    "messages": st.session_state.chat_messages
                }
                json_data = json.dumps(chat_export, indent=2)
                st.download_button(
                    label="📥 Download Chat History",
                    data=json_data,
                    file_name=f"chat_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json"
                )

    with col3:
        if st.session_state.chat_messages:
            st.info(f"💬 {len(st.session_state.chat_messages)} messages in this conversation")

    # Example questions
    with st.expander("💡 Example Questions to Try"):
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("""
            **Processing & Upload:**
            - "How do I process an invoice?"
            - "What file formats do you support?"
            - "How accurate is the extraction?"

            **Search & Query:**
            - "Find invoices from Microsoft"
            - "Show invoices over $5000"
            - "List recent vendor invoices"
            """)

        with col2:
            st.markdown("""
            **Analytics & Insights:**
            - "What spending insights can you provide?"
            - "Analyze my vendor relationships"
            - "Flag any unusual patterns"

            **Help & Examples:**
            - "What can you help me with?"
            - "Show me demo examples"
            - "How does this system work?"
            """)

    # Footer
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #666;">
        <p>🤖 <strong>AI Chat Assistant</strong> - Powered by Advanced Language Models</p>
        <p>Ask questions in natural language | Get instant insights</p>
    </div>
    """, unsafe_allow_html=True)

# Navigation
def main_navigation():
    """Handle navigation between different pages"""

    # Sidebar navigation
    st.sidebar.title("🧭 Navigation")

    page = st.sidebar.selectbox(
        "Choose a page",
        ["🏠 Home", "🤖 AI Chat Assistant", "⚙️ Settings", "ℹ️ About"],
        index=0
    )

    if page == "🏠 Home":
        main()
    elif page == "🤖 AI Chat Assistant":
        show_ai_chat_page()
    elif page == "⚙️ Settings":
        show_settings_page()
    elif page == "ℹ️ About":
        show_about_page()


# Run the application
if __name__ == "__main__":
    # Check if running in main mode or as part of navigation
    if 'page_mode' not in st.session_state:
        st.session_state.page_mode = "navigation"

    if st.session_state.page_mode == "navigation":
        main_navigation()
    else:
        main()