"""
CV parsing tool — extracts structured profile data from PDF/DOCX files.

Uses PyPDF2 (PDF) and python-docx (DOCX) for text extraction,
then passes the raw text through the LLM for structured extraction.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import get_settings
from app.domain.entities import Candidate

settings = get_settings()


class CVParserTool:
    """
    Parses CV/resume files and extracts structured candidate profiles.

    Pipeline:
    1. Extract raw text from PDF or DOCX
    2. Send to LLM for structured extraction
    3. Return Candidate entity (not persisted until user confirms)
    """

    @staticmethod
    def extract_text_from_pdf(file_path: str) -> str:
        """Extract text from a PDF file using PyMuPDF."""
        import fitz  # PyMuPDF

        pages = []
        with fitz.open(file_path) as doc:
            for page in doc:
                text = page.get_text()
                if text:
                    pages.append(text)
        return "\n".join(pages)

    @staticmethod
    def extract_text_from_docx(file_path: str) -> str:
        """Extract text from a DOCX file."""
        from docx import Document

        doc = Document(file_path)
        return "\n".join(para.text for para in doc.paragraphs if para.text.strip())

    @staticmethod
    def extract_text(file_path: str) -> str:
        """Route to the correct extractor based on file extension."""
        ext = Path(file_path).suffix.lower()
        if ext == ".pdf":
            return CVParserTool.extract_text_from_pdf(file_path)
        elif ext == ".docx":
            return CVParserTool.extract_text_from_docx(file_path)
        else:
            raise ValueError(f"Unsupported file type: {ext}")

    async def parse(
        self,
        tenant_id: uuid.UUID,
        file_path: str,
        filename: str,
    ) -> Candidate:
        """
        Full parsing pipeline:
        1. Extract text
        2. LLM-based structured extraction
        3. Return Candidate entity
        """
        raw_text = self.extract_text(file_path)
        structured = await self._extract_structured_data(raw_text)

        return Candidate(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            full_name=structured.get("full_name", "Unknown"),
            email=structured.get("email"),
            phone=structured.get("phone"),
            skills=structured.get("skills", []),
            experience=structured.get("experience", []),
            education=structured.get("education", []),
            projects=structured.get("projects", []),
            raw_text=raw_text[:5000],  # store first 5KB
            source_filename=filename,
            created_at=datetime.utcnow(),
        )

    async def _extract_structured_data(self, raw_text: str) -> Dict[str, Any]:
        """Use LLM to extract structured profile from raw text using with_structured_output()."""
        from pydantic import BaseModel, Field
        from typing import List, Optional
        from app.infrastructure.llm.langchain_provider import get_llm
        
        class Experience(BaseModel):
            title: str
            company: str
            duration: str
            description: str
            
        class Education(BaseModel):
            degree: str
            institution: str
            year: str
            
        class Project(BaseModel):
            name: str
            description: str
            technologies: List[str]
            
        class CandidateProfile(BaseModel):
            full_name: str
            email: Optional[str] = None
            phone: Optional[str] = None
            skills: List[str] = Field(default_factory=list)
            experience: List[Experience] = Field(default_factory=list)
            education: List[Education] = Field(default_factory=list)
            projects: List[Project] = Field(default_factory=list)

        llm = get_llm()
        structured_llm = llm.with_structured_output(CandidateProfile)
        
        prompt = (
            "Extract structured profile information from the following CV/resume text:\n\n"
            f"{raw_text[:4000]}\n"
        )

        try:
            result = await structured_llm.ainvoke(prompt)
            # Result is a Pydantic model
            return result.model_dump()
        except Exception:
            # Fallback: return basic structure
            return {
                "full_name": "Unknown",
                "skills": [],
                "experience": [],
                "education": [],
                "projects": [],
            }
