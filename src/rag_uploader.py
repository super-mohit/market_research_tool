# src/rag_uploader.py
"""
RAG Uploader Module for Market Research Intelligence

This module handles the uploading of market research artifacts to a RAG (Retrieval-Augmented Generation) system.
It creates collections, converts content to PDF format, uploads documents, and manages chat contexts.

Key Features:
- Collection creation with custom system prompts
- PDF conversion for all document types
- Document upload with proper metadata
- Chat context management for queries
- Preprocessing instructions setup
- Parallel document uploads for improved performance
"""

import requests
import json
import time
import tempfile
import os
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from src import config

# =============================================================================
# GLOBAL VARIABLES
# =============================================================================

# NOTE: Chat context management has been moved to the database.
# The query_rag_collection function is now stateless.

# Thread lock for thread-safe operations
upload_lock = threading.Lock()

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def _convert_to_pdf(json_data: dict, document_name: str) -> str:
    """
    Convert JSON data to a formatted PDF file and return the file path.

    Args:
        json_data (dict): The data to convert to PDF
        document_name (str): Name for the document (used in title and filename)

    Returns:
        str: Path to the generated PDF file
    """
    # Create a temporary file
    temp_fd, temp_path = tempfile.mkstemp(suffix='.pdf', prefix=f"{document_name}_")
    os.close(temp_fd)  # Close the file descriptor

    # Create PDF document
    doc = SimpleDocTemplate(temp_path, pagesize=letter, topMargin=1*inch)
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=12,
        alignment=TA_LEFT
    )

    content_style = ParagraphStyle(
        'CustomContent',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=6,
        alignment=TA_LEFT
    )

    # Build PDF content
    story = []

    # Add title
    story.append(Paragraph(f"Document: {document_name}", title_style))
    story.append(Spacer(1, 12))

    # Process the JSON data
    if 'content' in json_data:
        # For reports with content field
        content = json_data['content']
        # Split content into paragraphs for better formatting
        paragraphs = content.split('\n\n') if content else ['No content available']

        for para in paragraphs:
            if para.strip():
                # Escape HTML characters and handle markdown-like formatting
                clean_para = para.replace('&', '&').replace('<', '<').replace('>', '>')

                # Handle markdown bold formatting more carefully
                import re
                # Replace **text** with <b>text</b>
                clean_para = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', clean_para)
                # Replace single *text* with <i>text</i> (but not if it's part of **)
                clean_para = re.sub(r'(?<!\*)\*([^*]+?)\*(?!\*)', r'<i>\1</i>', clean_para)

                story.append(Paragraph(clean_para, content_style))
                story.append(Spacer(1, 6))
    elif 'items' in json_data:
        # For combined structured data with multiple items
        items = json_data['items']
        category = json_data.get('category', 'Items')

        story.append(Paragraph(f"Category: {category}", title_style))
        story.append(Spacer(1, 12))

        for i, item in enumerate(items, 1):
            story.append(Paragraph(f"<b>Item {i}:</b>", content_style))
            for key, value in item.items():
                if isinstance(value, str) and value.strip():
                    formatted_key = key.replace('_', ' ').title()
                    clean_value = value.replace('&', '&').replace('<', '<').replace('>', '>')
                    story.append(Paragraph(f"<b>{formatted_key}:</b> {clean_value}", content_style))
            story.append(Spacer(1, 8))
    else:
        # For structured data items
        for key, value in json_data.items():
            if key in ['title', 'type', 'summary', 'date', 'source_url']:
                formatted_key = key.replace('_', ' ').title()
                if isinstance(value, str):
                    clean_value = value.replace('&', '&').replace('<', '<').replace('>', '>')
                    story.append(Paragraph(f"<b>{formatted_key}:</b> {clean_value}", content_style))
                else:
                    story.append(Paragraph(f"<b>{formatted_key}:</b> {str(value)}", content_style))
                story.append(Spacer(1, 4))

    # Add metadata section
    story.append(Spacer(1, 12))
    story.append(Paragraph("Metadata:", title_style))

    # Add source type and other metadata
    for key, value in json_data.items():
        if key not in ['content', 'title', 'type', 'summary', 'date', 'source_url', 'items', 'category']:
            formatted_key = key.replace('_', ' ').title()
            clean_value = str(value).replace('&', '&').replace('<', '<').replace('>', '>')
            story.append(Paragraph(f"<b>{formatted_key}:</b> {clean_value}", content_style))

    # Build the PDF
    doc.build(story)

    return temp_path

def _combine_structured_data_by_category(extracted_data: dict) -> dict:
    """
    Combine structured data items by category into single documents.

    Args:
        extracted_data (dict): Dictionary with categories and their items

    Returns:
        dict: Combined documents by category
    """
    combined_docs = {}

    for category, items in extracted_data.items():
        if items:  # Only process categories that have items
            combined_docs[category.lower()] = {
                'category': category,
                'items': items,
                'source_type': f'combined_{category.lower()}',
                'item_count': len(items)
            }

    return combined_docs

# =============================================================================
# CORE API FUNCTIONS
# =============================================================================

def _create_rag_collection(collection_name: str, description: str):
    """
    Calls the /app/v2/CreateCollection endpoint using the actual API specification.

    Args:
        collection_name (str): Name for the new collection (without org prefix)
        description (str): Description of the collection

    Returns:
        dict: API response
    """
    headers = {
        "X-Api-Token": config.RAG_API_TOKEN,
        "x-orgId": config.RAG_API_ORG_ID,
        "X-Api-Org": config.RAG_API_ORG_ID
    }
    data = {
        "collectionName": collection_name,
        "collectionDescription": description,
        "jsonFields": "",  # Empty as shown in example
        "usertype": config.RAG_API_USER_TYPE,
        "base_language": "en",
        "source": "files",
        "model": "gpt-4o-mini",
        "response_language": "en"
    }
    url = f"{config.RAG_API_BASE_URL}/app/v2/CreateCollection"

    response = requests.post(url, headers=headers, data=data)
    if response.status_code != 200:
        print(f"❌ CreateCollection failed. Status: {response.status_code}")
        print(f"❌ Response: {response.text}")
    response.raise_for_status() # Raise an exception for HTTP errors
    return response.json()

def _update_system_prompt(collection_name: str):
    """
    Calls the /app/v2/UpdateSystemPrompt endpoint to set a custom system prompt for the collection.

    Args:
        collection_name (str): Name of the collection to update (with org prefix)

    Returns:
        dict: API response
    """
    headers = {
        "X-Api-Token": config.RAG_API_TOKEN,
        "x-orgId": config.RAG_API_ORG_ID,
        "X-Api-Org": config.RAG_API_ORG_ID
    }

    # Create a comprehensive system prompt for market research intelligence
    system_prompt = """You are an expert Market Intelligence Analyst, acting as an interactive query engine for a specific research job.

**Your Core Directives:**

1.  **Scope Limitation:** Your knowledge is strictly and absolutely limited to the documents uploaded for this research job. These include a final report, intermediate analyses, and structured data files (news, patents, etc.).

2.  **Answer First, Then Cite:** Respond directly to the user's question first. Then, you MUST provide precise citations that support your answer.
    - **Citation Format:** Refer to the source document by its logical name (e.g., `[final_report]`, `[intermediate_report_3]`, `[combined_news_data]`).

3.  **Synthesize and Analyze:** Do not just quote passages. Synthesize information from multiple sources if necessary to form a complete answer. When asked for an opinion or analysis (e.g., "What is the biggest threat?"), base your conclusion on the evidence within the documents.

4.  **Honesty and Transparency:** If you cannot answer a question using the provided documents, you MUST state that clearly. Do not hallucinate, speculate, or attempt to answer using external knowledge. A perfect answer is: "I cannot answer that question based on the provided documents."

5.  **Be Professional and Concise:** Use clear, structured language (headings, bullet points) to present your findings. Your purpose is to provide quick, reliable access to the key intelligence contained in the research artifacts.

**Example Interaction:**

User: "Which companies are leading in scuff-resistant coating technologies?"

You: "Based on the provided research, the key players in scuff-resistant coating technologies include Company A, who launched a new product line, and Company B, who was granted a relevant patent.

- Company A's "DuraShield" product showed a 50% improvement in abrasion tests according to the analysis. `[final_report]`
- Company B's patent focuses on a novel polymer cross-linking technology. `[combined_patents_data]`"
"""

    data = {
        "new_prompt": system_prompt,
        "partition_name": collection_name,
        "username": "mbhimrajka@supervity.ai"
    }

    url = f"{config.RAG_API_BASE_URL}/app/v2/UpdateSystemPrompt"

    response = requests.post(url, headers=headers, data=data)
    if response.status_code != 200:
        print(f"❌ UpdateSystemPrompt failed. Status: {response.status_code}")
        print(f"❌ Response: {response.text}")
    response.raise_for_status()
    return response.json()

def _set_preprocess_instructions(collection_name: str):
    """
    Calls the /app/v2/PreprocessInstruct endpoint to set preprocessing instructions for the collection.

    Args:
        collection_name (str): Name of the collection to configure (with org prefix)

    Returns:
        dict: API response
    """
    headers = {
        "X-Api-Token": config.RAG_API_TOKEN,
        "x-orgId": config.RAG_API_ORG_ID,
        "X-Api-Org": config.RAG_API_ORG_ID
    }

    # Create preprocessing instructions for market research data
    preprocess_instructions = """Please find below the key preprocessing guidelines for market research intelligence analysis:

1. **Document Structure**: Identify document types (final reports, intermediate reports, news articles, patents, conference papers) and structure the analysis accordingly.

2. **Data Categorization**: Organize information into relevant categories:
   - Market trends and forecasts
   - Competitive intelligence
   - Technological innovations
   - Regulatory changes
   - Industry dynamics

3. **Key Information Extraction**: Focus on extracting:
   - Market size and growth projections
   - Key players and market share data
   - Emerging technologies and innovations
   - Geographic market insights
   - Regulatory and compliance factors
   - Investment and funding activities

4. **Source Credibility**: Prioritize information based on source reliability and recency of data.

5. **Cross-Reference Analysis**: Identify patterns and correlations across multiple sources and document types.

6. **Date Sensitivity**: Pay attention to publication dates and ensure temporal relevance of insights.

7. **Quantitative Data**: Extract and highlight numerical data, percentages, market valuations, and statistical information.

8. **Actionable Intelligence**: Focus on information that provides strategic value and business decision support.

9. **Citation Preparation**: Maintain document source information for proper attribution in responses.

10. **Context Preservation**: Maintain the relationship between the original research query and the extracted information."""

    data = {
        "partition_name": collection_name,
        "username": "mbhimrajka@supervity.ai",
        "preprocess_instruct": preprocess_instructions
    }

    url = f"{config.RAG_API_BASE_URL}/app/v2/PreprocessInstruct"

    response = requests.post(url, headers=headers, data=data)
    if response.status_code != 200:
        print(f"❌ PreprocessInstruct failed. Status: {response.status_code}")
        print(f"❌ Response: {response.text}")
    response.raise_for_status()
    return response.json()

def _upload_document(collection_name: str, document_name: str, json_data: dict):
    """
    Calls the /app/v2/UploadDocument endpoint using the actual API specification.
    Converts content to PDF before uploading.

    Args:
        collection_name (str): Name of the collection to upload to (with org prefix)
        document_name (str): Name for the document
        json_data (dict): Data to convert and upload

    Returns:
        dict: API response with success/failure info
    """
    headers = {
        "X-Api-Token": config.RAG_API_TOKEN,
        "x-orgId": config.RAG_API_ORG_ID,
        "X-Api-Org": config.RAG_API_ORG_ID
    }

    # Convert content to PDF
    pdf_file_path = _convert_to_pdf(json_data, document_name)

    try:
        # Upload the PDF file
        with open(pdf_file_path, 'rb') as pdf_file:
            files = {
                'document': (f"{document_name}.pdf", pdf_file, 'application/pdf')
            }
            data = {
                "collectionName": collection_name,
                "jsonData": "",  # Empty as shown in example
                "documentName": document_name,
                "usertype": config.RAG_API_USER_TYPE,
                "useOCR": "false"
            }

            url = f"{config.RAG_API_BASE_URL}/app/v2/UploadDocument"

            # Debug: Show file size
            pdf_file.seek(0, 2)  # Go to end
            file_size = pdf_file.tell()
            pdf_file.seek(0)  # Go back to start

            with upload_lock:
                print(f"   → Uploading PDF: {document_name}.pdf ({file_size:,} bytes)")

            response = requests.post(url, headers=headers, data=data, files=files)

            if response.status_code != 200:
                with upload_lock:
                    print(f"   ❌ Upload failed for {document_name}. Status: {response.status_code}")
                    print(f"   ❌ Response: {response.text}")
                return {"success": False, "document_name": document_name, "error": response.text}

            with upload_lock:
                print(f"   ✅ Upload successful: {document_name}")
            return {"success": True, "document_name": document_name, "response": response.json()}

    except Exception as e:
        with upload_lock:
            print(f"   ❌ Upload failed for {document_name}. Error: {e}")
        return {"success": False, "document_name": document_name, "error": str(e)}
    finally:
        # Clean up the temporary PDF file
        if os.path.exists(pdf_file_path):
            os.remove(pdf_file_path)

def query_rag_collection(collection_name: str, question: str, current_chat_context: str = "") -> dict:
    """
    Calls the /app/v2/QueryDocument endpoint.
    Manages chat context via passed-in arguments, it is STATELESS.

    Args:
        collection_name (str): Name of the collection to query
        question (str): Question to ask the RAG system
        current_chat_context (str): The conversation history from the database.

    Returns:
        dict: The full RAG response payload from the API.
    """
    config.assert_rag_env()
    print(f"Querying RAG collection '{collection_name}' with question: '{question}'")
    print(f"   -> Sending chat context (length: {len(current_chat_context)} chars)")

    headers = {
        "X-Api-Token": config.RAG_API_TOKEN,
        "x-orgId": config.RAG_API_ORG_ID,
        "X-Api-Org": config.RAG_API_ORG_ID
    }
    
    data = {
        "question": question,
        "collectionName": collection_name,
        "jsonData": "",
        "documentName": "",
        "usertype": config.RAG_API_USER_TYPE,
        "chat_context": current_chat_context
    }

    url = f"{config.RAG_API_BASE_URL}/app/v2/QueryDocument"

    try:
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        result = response.json()
        
        # The function is now stateless. It just returns the result.
        # The caller is responsible for updating the context.
        print(f"   -> Received response from RAG API.")
        return result
        
    except requests.exceptions.HTTPError as e:
        print(f"Error querying RAG. Status: {e.response.status_code}, Body: {e.response.text}")
        raise e


# =============================================================================
# MAIN ORCHESTRATION FUNCTION
# =============================================================================

def upload_artifacts_to_rag(job_id: str, artifacts: dict):
    """
    Main function to upload research artifacts to the RAG system with parallel uploads.

    This function orchestrates the complete upload process:
    1. Creates a new collection
    2. Sets up system prompt and preprocessing instructions
    3. Uploads final report, intermediate reports, and structured data in parallel
    4. Initializes chat context for future queries

    Args:
        job_id (str): Unique identifier for the research job
        artifacts (dict): Dictionary containing all research artifacts

    Returns:
        str or None: Collection name if successful, None if failed
    """
    try:
        config.assert_rag_env()
        print(f"--- Starting RAG Upload for Job ID: {job_id} ---")

        # 1. Create a new collection for this job
        base_collection_name = f"research_job_{job_id.replace('-', '_')}"
        collection_description = f"Artifacts for research query: {artifacts['original_query'][:100]}"

        _create_rag_collection(base_collection_name, collection_description)
        print(f"-> RAG: Created collection '{base_collection_name}'.")

        # 2. For subsequent operations, use the full collection name with org prefix
        full_collection_name = f"{config.RAG_API_ORG_ID}_{base_collection_name}"

        # 3. Configure collection settings
        _update_system_prompt(full_collection_name)
        print(f"-> RAG: Updated system prompt for '{full_collection_name}'.")

        _set_preprocess_instructions(full_collection_name)
        print(f"-> RAG: Set preprocessing instructions for '{full_collection_name}'.")

        # 4. Prepare all upload tasks
        upload_tasks = []

        # Add final report to upload tasks
        upload_tasks.append(("final_report", {
            "content": artifacts['final_report_markdown'],
            "source_type": "final_report"
        }))

        # Add job-specific intermediate reports to upload tasks
        if 'intermediate_reports' in artifacts and artifacts['intermediate_reports']:
            for i, intermediate_report in enumerate(artifacts['intermediate_reports']):
                upload_tasks.append((f"intermediate_report_{i}", {
                    "content": intermediate_report,
                    "source_type": "intermediate_report",
                    "report_index": i
                }))

        # Combine structured data by category and add to upload tasks
        extracted_data = artifacts['extracted_data']
        combined_docs = _combine_structured_data_by_category(extracted_data)

        for category, combined_data in combined_docs.items():
            upload_tasks.append((f"combined_{category}", combined_data))

        # 5. Execute all uploads in parallel
        print(f"-> RAG: Starting parallel upload of {len(upload_tasks)} documents...")

        successful_uploads = 0
        failed_uploads = 0

        with ThreadPoolExecutor(max_workers=5) as executor:  # Limit concurrent uploads
            # Submit all upload tasks
            future_to_task = {
                executor.submit(_upload_document, full_collection_name, task_name, task_data): (task_name, task_data)
                for task_name, task_data in upload_tasks
            }

            # Process completed uploads
            for future in as_completed(future_to_task):
                task_name, task_data = future_to_task[future]
                try:
                    result = future.result()
                    if result.get("success"):
                        successful_uploads += 1
                    else:
                        failed_uploads += 1
                        print(f"   ❌ Failed to upload {task_name}: {result.get('error', 'Unknown error')}")
                except Exception as e:
                    failed_uploads += 1
                    print(f"   ❌ Exception during upload of {task_name}: {e}")

        # 6. Chat context is now managed by the database, no initialization needed

        # 7. Summary
        total_items = len(combined_docs)
        intermediate_count = len(artifacts.get('intermediate_reports', []))

        print(f"--- RAG Upload Complete ---")
        print(f"   Collection: '{full_collection_name}'")
        print(f"   Successful uploads: {successful_uploads}")
        print(f"   Failed uploads: {failed_uploads}")
        print(f"   Final report: 1, Intermediate reports: {intermediate_count}, Combined categories: {total_items}")
        print(f"--- Total documents uploaded: {successful_uploads} ---")

        if failed_uploads > 0:
            print(f"⚠️  Warning: {failed_uploads} uploads failed")

        return full_collection_name if successful_uploads > 0 else None

    except Exception as e:
        print(f"❌ RAG Upload Failed for Job ID: {job_id}. Error: {e}")
        return None

# =============================================================================
#   🧪 REALISTIC TESTING WITH ACTUAL PIPELINE FILES
# =============================================================================

def main():
    """
    Test the entire RAG pipeline using actual files from the market research pipeline.
    
    This function:
    1. Reads a real final report from the reports/ directory
    2. Loads job-specific intermediate reports from reports/intermediate_reports/
    3. Loads real extracted data from extractions/ directory 
    4. Tests the complete upload and query workflow with realistic data
    """
    import json
    import glob
    import os
    from pathlib import Path
    import re
    
    print("🧪 Testing RAG Pipeline with Actual Market Research Files")
    print("=" * 70)
    
    # ─────────────────────────────────────────────────────────────────────────────────────────
    # 1. Load actual final report from reports directory
    # ─────────────────────────────────────────────────────────────────────────────────────────
    
    reports_dir = Path("reports")
    final_reports = list(reports_dir.glob("*FINAL_REPORT.md"))
    
    if not final_reports:
        print("❌ No final reports found in reports/ directory")
        return
    
    # Use the most recent final report
    latest_report = max(final_reports, key=lambda x: x.stat().st_mtime)
    print(f"📄 Using final report: {latest_report.name}")
    
    try:
        with open(latest_report, 'r', encoding='utf-8') as f:
            final_report_content = f.read()
        print(f"   ✓ Loaded final report ({len(final_report_content):,} characters)")
    except Exception as e:
        print(f"❌ Error reading final report: {e}")
        return
    
    # ─────────────────────────────────────────────────────────────────────────────────────────
    # 2. Extract job ID from filename and load job-specific intermediate reports
    # ─────────────────────────────────────────────────────────────────────────────────────────
    
    # Extract UUID from filename (e.g., "20250616_114604_e8ba587e71d8fe26_FINAL_REPORT.md")
    uuid_match = re.search(r'([a-f0-9]{16})', latest_report.name)
    if uuid_match:
        job_uuid = uuid_match.group(1)
        job_id = f"{job_uuid}-71d8-fe26-1234-123456789abc"  # Extend to full UUID format
    else:
        job_id = "test-pipeline-12345678-1234-5678-9abc-123456789def"
    
    print(f"🔑 Using Job ID: {job_id}")
    print(f"🔍 Looking for intermediate reports with UUID: {job_uuid}")
    
    # Load only job-specific intermediate reports
    intermediate_dir = reports_dir / "intermediate_reports"
    intermediate_files = list(intermediate_dir.glob(f"*{job_uuid}*.md"))  # Filter by job UUID
    
    intermediate_reports = []
    for file_path in intermediate_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                intermediate_reports.append(content)
            print(f"   ✓ Loaded job-specific intermediate report: {file_path.name}")
        except Exception as e:
            print(f"   ⚠️  Failed to load {file_path.name}: {e}")
    
    print(f"📊 Loaded {len(intermediate_reports)} job-specific intermediate reports")
    
    # ─────────────────────────────────────────────────────────────────────────────────────────
    # 3. Load actual extracted data from JSON files
    # ─────────────────────────────────────────────────────────────────────────────────────────
    
    extractions_dir = Path("extractions")
    extraction_files = list(extractions_dir.glob("*.json"))
    
    if not extraction_files:
        print("❌ No extraction files found in extractions/ directory")
        return
    
    # Use the most recent extraction file
    latest_extraction = max(extraction_files, key=lambda x: x.stat().st_mtime)
    print(f"📊 Using extraction data: {latest_extraction.name}")
    
    try:
        with open(latest_extraction, 'r', encoding='utf-8') as f:
            extraction_data = json.load(f)
        
        # Validate the structure
        if 'extracted_data' not in extraction_data:
            print("❌ Invalid extraction file structure - missing 'extracted_data'")
            return
            
        extracted_items = extraction_data['extracted_data']
        metadata = extraction_data.get('metadata', {})
        
        print(f"   ✓ Loaded extraction data with categories: {list(extracted_items.keys())}")
        print(f"   ✓ Metadata: {metadata.get('total_items_extracted', 'unknown')} total items")
        
        # Show category breakdown
        for category, items in extracted_items.items():
            print(f"     - {category}: {len(items)} items")
        
    except Exception as e:
        print(f"❌ Error loading extraction data: {e}")
        return
    
    # ─────────────────────────────────────────────────────────────────────────────────────────
    # 4. Create realistic artifacts structure
    # ─────────────────────────────────────────────────────────────────────────────────────────
    
    # Get original query from metadata or use a default
    original_query = metadata.get('original_query', 
        """Show me the latest innovations in Weatherability of Decorative Coatings.
What trends are emerging in the Sustainability of industrial coatings in 2025?
Find recent conferences or Patents discussing Scuff-Resistance in coatings.

Search tags/topics - Product, coating, architectural or similar.""")
    
    artifacts = {
        'original_query': original_query,
        'final_report_markdown': final_report_content,
        'intermediate_reports': intermediate_reports,
        'extracted_data': extracted_items,
        'metadata': metadata
    }
    
    print(f"\n📦 Artifacts Summary:")
    print(f"   • Final Report: {len(final_report_content):,} characters")
    print(f"   • Job-Specific Intermediate Reports: {len(intermediate_reports)} files")
    print(f"   • Extracted Data Categories: {len(extracted_items)}")
    for category, items in extracted_items.items():
        print(f"     - {category}: {len(items)} items → will be combined into 1 document")
    
    # ─────────────────────────────────────────────────────────────────────────────────────────
    # 5. Test the complete upload pipeline
    # ─────────────────────────────────────────────────────────────────────────────────────────
    
    print(f"\n🚀 Starting RAG Upload Pipeline...")
    collection_name = upload_artifacts_to_rag(job_id, artifacts)
    
    if not collection_name:
        print("❌ RAG upload failed!")
        return
    
    # ─────────────────────────────────────────────────────────────────────────────────────────
    # 6. Test query functionality with business-relevant questions
    # ─────────────────────────────────────────────────────────────────────────────────────────
    
    test_queries = [
        "What are the latest innovations in weatherability for decorative coatings?",
        "What sustainability trends are emerging in industrial coatings for 2025?",
        "Which companies are leading in scuff-resistant coating technologies?",
        "What are the key patents and conferences related to coating durability?",
        "How is the global coatings market projected to grow through 2032?"
    ]
    
    print(f"\n🔍 Testing Query Functionality...")
    print("-" * 50)
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n{i}. Query: {query}")
        response = query_rag_collection(collection_name, query)
        
        if response:
            # Truncate long responses for readability
            response_text = response.get('response', str(response))
            display_response = response_text[:300] + "..." if len(response_text) > 300 else response_text
            print(f"   ✓ Response: {display_response}")
        else:
            print(f"   ❌ Query failed")
        
        # Small delay between queries
        time.sleep(1)
    
    print(f"\n✅ RAG Pipeline Test Complete!")
    print(f"   Collection: {collection_name}")
    print(f"   Total Queries: {len(test_queries)}")
    print("=" * 70)


if __name__ == "__main__":
    main() 