"""Google Document AI client: the one place the app talks to the processor.

Configuration comes from the environment (``.env`` is loaded on import):
``GCP_PROJECT_ID``, ``GCP_LOCATION``, ``GCP_PROCESSOR_ID`` and
``GOOGLE_APPLICATION_CREDENTIALS`` (path to a service-account key file).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv
from google.api_core.client_options import ClientOptions
from google.cloud import documentai

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    project_id: str
    location: str
    processor_id: str


def settings() -> Settings:
    return Settings(
        project_id=os.getenv("GCP_PROJECT_ID", "invoiceprocessingai2498"),
        location=os.getenv("GCP_LOCATION", "us"),
        processor_id=os.getenv("GCP_PROCESSOR_ID", "cca0593594bfdba1"),
    )


def credentials_available() -> bool:
    path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    return bool(path) and os.path.exists(path)


@lru_cache(maxsize=1)
def get_client() -> documentai.DocumentProcessorServiceClient:
    """Client on the processor's regional endpoint. Raises ``RuntimeError`` if
    the credentials file is not configured (failures are not cached)."""
    if not credentials_available():
        raise RuntimeError("Google Cloud credentials not found (GOOGLE_APPLICATION_CREDENTIALS="
                           f"{os.getenv('GOOGLE_APPLICATION_CREDENTIALS')!r})")
    s = settings()
    opts = ClientOptions(api_endpoint=f"{s.location}-documentai.googleapis.com")
    client = documentai.DocumentProcessorServiceClient(client_options=opts)
    logger.info("Document AI client ready: project %s, location %s, processor %s",
                s.project_id, s.location, s.processor_id)
    return client


def processor_name() -> str:
    s = settings()
    return get_client().processor_path(s.project_id, s.location, s.processor_id)


def process_bytes(content: bytes, mime_type: str) -> documentai.Document:
    """Send one file to the processor (one billable call) and return its Document."""
    request = documentai.ProcessRequest(
        name=processor_name(),
        raw_document=documentai.RawDocument(content=content, mime_type=mime_type),
    )
    result = get_client().process_document(request=request)
    logger.info("Document processed: %d pages, %d entities",
                len(result.document.pages), len(result.document.entities))
    return result.document
