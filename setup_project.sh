#!/bin/bash
# setup_project.sh - Creates complete project structure

echo "🚀 Setting up Invoice Processing AI project structure..."

# Create main directories
mkdir -p src/{api,core,database,utils}
mkdir -p frontend/components
mkdir -p tests/{unit,integration}
mkdir -p data/{sample_documents,models}
mkdir -p scripts
mkdir -p docs
mkdir -p docker

# Create __init__.py files for Python packages
touch src/__init__.py
touch src/api/__init__.py
touch src/core/__init__.py
touch src/database/__init__.py
touch src/utils/__init__.py
touch tests/__init__.py

# Create essential configuration files
cat > .env.example << 'EOF'
# Google Cloud Platform
GCP_PROJECT_ID=tidal-osprey-463403-r3
GCP_LOCATION=us
GCP_PROCESSOR_ID=cc2b2b72d00219a1
GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account.json

# Database
DATABASE_URL=sqlite:///./invoice_processing.db

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=True

# ML Configuration
MODEL_PATH=data/models/document_classifier.pkl
MIN_CONFIDENCE_THRESHOLD=0.7

# File Upload
MAX_FILE_SIZE=10485760
UPLOAD_DIR=uploads
EOF

# Create .gitignore
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Environment
.env
.venv
env/
venv/
ENV/
env.bak/
venv.bak/

# IDEs
.vscode/
.idea/
*.swp
*.swo
*~

# Database
*.db
*.sqlite
*.sqlite3

# Logs
*.log
logs/

# OS
.DS_Store
Thumbs.db

# Project specific
uploads/
data/models/*.pkl
*.json
!data/sample_documents/
node_modules/

# Google Cloud
service-account*.json
gcp-key*.json
EOF

echo "✅ Project structure created!"
echo "📁 Created directories:"
find . -type d -name ".*" -prune -o -type d -print | sort

echo ""
echo "🔧 Next steps:"
echo "1. Copy .env.example to .env and configure your settings"
echo "2. Run: pip install -r requirements.txt"
echo "3. Set up your Google Cloud credentials"
echo "4. Start implementing the core modules"