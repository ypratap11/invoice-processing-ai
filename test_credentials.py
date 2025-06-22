"""
Test Google Cloud credentials
"""
import os
from google.cloud import documentai


def test_credentials():
    print("🔍 Testing Google Cloud Credentials...")

    # Check if file exists
    cred_file = "invoice-processor-key.json"
    if os.path.exists(cred_file):
        print(f"✅ Credentials file found: {cred_file}")
        print(f"   File size: {os.path.getsize(cred_file)} bytes")
    else:
        print(f"❌ Credentials file not found: {cred_file}")
        print(f"   Current directory: {os.getcwd()}")
        print(f"   Files in directory: {os.listdir('.')}")
        return False

    # Set environment variable manually
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = cred_file
    print(f"✅ Set GOOGLE_APPLICATION_CREDENTIALS to: {cred_file}")

    # Try to initialize client
    try:
        client = documentai.DocumentProcessorServiceClient()
        print("✅ Document AI client initialized successfully!")

        # Test processor path
        project_id = "invoiceprocessingai2498"
        location = "us"
        processor_id = "cca0593594bfdba1"

        processor_path = client.processor_path(project_id, location, processor_id)
        print(f"✅ Processor path created: {processor_path}")

        return True

    except Exception as e:
        print(f"❌ Failed to initialize client: {str(e)}")
        return False


if __name__ == "__main__":
    test_credentials()