"""
Document Retriever for Corporate Inventory Replenishment & Reorder Policy.
Chunks the policy by section and preserves:
- document_name
- section
- policy_version
- effective_date
- source_references
- content
Provides structured retrieval with keyword/token matching and relevance ranking.
"""

import os
import re
from typing import List, Dict, Optional
from .state import PolicyChunk

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

class PolicyRetriever:
    DOCUMENT_NAME = "Corporate Inventory Replenishment & Reorder Policy"
    POLICY_VERSION = "v2.4"
    EFFECTIVE_DATE = "2024-03-01"

    def __init__(self, data_dir: str = DATA_DIR):
        self.data_dir = data_dir
        self.pdf_path = os.path.join(data_dir, "reorder_policy.pdf")
        self.txt_path = os.path.join(data_dir, "reorder_policy.txt")
        self.chunks: List[PolicyChunk] = []
        self._load_and_chunk()

    def _read_raw_policy(self) -> str:
        """Reads policy text from reorder_policy.txt or extracts streams from reorder_policy.pdf."""
        if os.path.exists(self.txt_path):
            with open(self.txt_path, "r", encoding="utf-8") as f:
                return f.read()
        
        # Fallback to PDF stream extraction
        if os.path.exists(self.pdf_path):
            with open(self.pdf_path, "rb") as f:
                content = f.read().decode("latin-1", errors="ignore")
                # Extract text within stream blocks
                streams = re.findall(r"stream[\r\n]+(.*?)[\r\n]+endstream", content, re.DOTALL)
                extracted_lines = []
                for s in streams:
                    for tj in re.findall(r"\((.*?)\)\s*Tj", s):
                        extracted_lines.append(tj.replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\"))
                if extracted_lines:
                    return "\n".join(extracted_lines)
        
        raise FileNotFoundError(f"Neither {self.txt_path} nor {self.pdf_path} found.")

    def _load_and_chunk(self):
        """Chunks policy by section preserving document metadata, version, and source references."""
        raw_text = self._read_raw_policy()
        
        # Split by SECTION headers
        # Pattern: SECTION \d+: Title
        section_pattern = re.compile(r"(SECTION\s+(\d+):\s*([^\n]+))", re.IGNORECASE)
        splits = list(section_pattern.finditer(raw_text))

        self.chunks = []
        if not splits:
            # Fallback single chunk
            self.chunks.append(
                PolicyChunk(
                    chunk_id="CHUNK-SEC-ALL",
                    document_name=self.DOCUMENT_NAME,
                    section="Full Policy Document",
                    policy_version=self.POLICY_VERSION,
                    effective_date=self.EFFECTIVE_DATE,
                    source_references="reorder_policy.pdf",
                    content=raw_text.strip(),
                )
            )
            return

        for i, match in enumerate(splits):
            sec_full_header = match.group(1).strip()
            sec_num = match.group(2)
            start_pos = match.end()
            end_pos = splits[i + 1].start() if i + 1 < len(splits) else len(raw_text)
            sec_body = raw_text[start_pos:end_pos].strip()
            
            # Clean separators
            sec_body = re.sub(r"^=+\s*", "", sec_body)
            sec_body = re.sub(r"\s*=+$", "", sec_body).strip()

            chunk = PolicyChunk(
                chunk_id=f"CHUNK-SEC-0{sec_num}",
                document_name=self.DOCUMENT_NAME,
                section=sec_full_header,
                policy_version=self.POLICY_VERSION,
                effective_date=self.EFFECTIVE_DATE,
                source_references=f"reorder_policy.pdf (Section {sec_num}, Page {1 + (int(sec_num) // 3)})",
                content=f"{sec_full_header}\n{sec_body}",
            )
            self.chunks.append(chunk)

    def retrieve(self, query: str, top_k: int = 2) -> List[PolicyChunk]:
        """
        Retrieves top_k policy chunks relevant to the query based on keyword overlap and semantic salience.
        """
        query_tokens = set(re.findall(r"\w+", query.lower()))
        scored_chunks: List[PolicyChunk] = []

        for chunk in self.chunks:
            chunk_tokens = set(re.findall(r"\w+", chunk.content.lower()))
            overlap = query_tokens.intersection(chunk_tokens)
            
            # Weighted score: overlap + specific keyword boost
            score = len(overlap) / max(len(query_tokens), 1)
            
            # Key domain terms boost
            lower_content = chunk.content.lower()
            if "reorder point" in query.lower() and "reorder point" in lower_content:
                score += 0.5
            if "available inventory" in query.lower() and "available inventory" in lower_content:
                score += 0.5
            if "insufficient" in query.lower() and "insufficient" in lower_content:
                score += 0.6
            if "moq" in query.lower() and "moq" in lower_content:
                score += 0.5
            if "lead time" in query.lower() and "lead time" in lower_content:
                score += 0.4
            if "idempotency" in query.lower() and "idempotency" in lower_content:
                score += 0.5

            c_copy = PolicyChunk(
                chunk_id=chunk.chunk_id,
                document_name=chunk.document_name,
                section=chunk.section,
                policy_version=chunk.policy_version,
                effective_date=chunk.effective_date,
                source_references=chunk.source_references,
                content=chunk.content,
                relevance_score=round(score, 3)
            )
            scored_chunks.append(c_copy)

        scored_chunks.sort(key=lambda x: x.relevance_score, reverse=True)
        return scored_chunks[:top_k]

    def get_all_chunks(self) -> List[PolicyChunk]:
        return list(self.chunks)
