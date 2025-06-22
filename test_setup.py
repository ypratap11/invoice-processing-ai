"""
Comprehensive test script for the invoice processing system
"""
import os
import sys


def test_imports():
    """Test all required imports"""
    print("📦 Testing Package Imports...")
    print("-" * 40)

    packages = [
        ('FastAPI', 'fastapi'),
        ('Uvicorn', 'uvicorn'),
        ('Google Cloud Document AI', 'google.cloud.documentai'),
        ('Pydantic', 'pydantic'),
        ('Scikit-learn', 'sklearn'),
        ('Pandas', 'pandas'),
        ('NumPy', 'numpy'),
        ('Streamlit', 'streamlit'),
    ]

    all_good = True
    for name, package in packages:
        try:
            __import__(package)
            print(f"✅ {name}")
        except ImportError:
            print(f"❌ {name}")
            all_good = False

    return all_good


def test_configuration():
    """Test configuration loading"""
    print("\n⚙️ Testing Configuration...")
    print("-" * 40)

    try:
        from src.utils.config import get_settings
        settings = get_settings()

        print(f"✅ Configuration loaded")
        print(f"   Project ID: {settings.GCP_PROJECT_ID}")
        print(f"   Processor ID: {settings.GCP_PROCESSOR_ID}")
        print(f"   Location: {settings.GCP_LOCATION}")

        return True
    except Exception as e:
        print(f"❌ Configuration failed: {str(e)}")
        return False


def test_document_processor():
    """Test Document AI processor"""
    print("\n🤖 Testing Document AI Processor...")
    print("-" * 40)

    try:
        from src.core.document_processor import test_processor
        return test_processor()
    except Exception as e:
        print(f"❌ Document processor test failed: {str(e)}")
        return False


def test_classifier():
    """Test ML classifier"""
    print("\n🧠 Testing ML Classifier...")
    print("-" * 40)

    try:
        from src.core.classifier import test_classifier
        return test_classifier()
    except Exception as e:
        print(f"❌ Classifier test failed: {str(e)}")
        return False


def test_project_structure():
    """Test project structure"""
    print("\n📁 Testing Project Structure...")
    print("-" * 40)

    required_dirs = [
        'src', 'src/api', 'src/core', 'src/database', 'src/utils',
        'data', 'tests', 'scripts', 'frontend'
    ]

    all_dirs_exist = True
    for dir_path in required_dirs:
        if os.path.exists(dir_path):
            print(f"✅ {dir_path}/")
        else:
            print(f"❌ {dir_path}/ missing")
            all_dirs_exist = False

    return all_dirs_exist


def main():
    """Run all tests"""
    print("🚀 Invoice Processing AI - Complete System Test")
    print("=" * 60)

    tests = [
        ("Project Structure", test_project_structure),
        ("Package Imports", test_imports),
        ("Configuration", test_configuration),
        ("Document Processor", test_document_processor),
        ("ML Classifier", test_classifier),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with error: {str(e)}")
            results.append((test_name, False))

    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)

    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
        if result:
            passed += 1

    print(f"\nResults: {passed}/{len(results)} tests passed")

    if passed == len(results):
        print("\n🎉 ALL TESTS PASSED!")
        print("🚀 Your AI system is ready for development!")
        print("\n📝 Next steps:")
        print("  1. Set up your .env file with GCP credentials")
        print("  2. Test with a real document")
        print("  3. Build the FastAPI endpoints")
        print("  4. Create the Streamlit frontend")
    else:
        print(f"\n⚠️  {len(results) - passed} tests failed")
        print("Fix the failing components before proceeding")


if __name__ == "__main__":
    main()