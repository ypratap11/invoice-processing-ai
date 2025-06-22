version: '3.8'

services:
  # FastAPI Backend Service
  api:
    build:
      context: .
      dockerfile: Dockerfile
      target: backend
    container_name: invoice-ai-backend
    ports:
      - "8000:8000"
    environment:
      - GCP_PROJECT_ID=${GCP_PROJECT_ID}
      - GCP_LOCATION=${GCP_LOCATION}
      - GCP_PROCESSOR_ID=${GCP_PROCESSOR_ID}
      - GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json
      - API_HOST=0.0.0.0
      - API_PORT=8000
      - DEBUG=true
    volumes:
      - ./invoice-processor-key.json:/app/credentials.json:ro
      - ./uploads:/app/uploads
      - ./logs:/app/logs
    env_file:
      - .env
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    restart: unless-stopped
    networks:
      - invoice-ai-network

  # Streamlit Frontend Service
  frontend:
    build:
      context: .
      dockerfile: Dockerfile
      target: frontend
    container_name: invoice-ai-frontend
    ports:
      - "8501:8501"
    environment:
      - API_BASE_URL=http://api:8000
      - STREAMLIT_SERVER_PORT=8501
      - STREAMLIT_SERVER_ADDRESS=0.0.0.0
    depends_on:
      api:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8501/_stcore/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    networks:
      - invoice-ai-network

  # Optional: Redis for caching and session management
  redis:
    image: redis:7-alpine
    container_name: invoice-ai-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped
    networks:
      - invoice-ai-network
    command: redis-server --appendonly yes

  # Optional: PostgreSQL for production database
  postgres:
    image: postgres:15-alpine
    container_name: invoice-ai-postgres
    environment:
      POSTGRES_DB: invoice_processing
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres123}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"
    restart: unless-stopped
    networks:
      - invoice-ai-network

  # Optional: Nginx reverse proxy for production
  nginx:
    image: nginx:alpine
    container_name: invoice-ai-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - api
      - frontend
    restart: unless-stopped
    networks:
      - invoice-ai-network

# Named volumes for data persistence
volumes:
  postgres_data:
    driver: local
  redis_data:
    driver: local

# Custom network for service communication
networks:
  invoice-ai-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16