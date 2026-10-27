"""
Policy Relevance Grader and Bounded Query Rewriter.
Evaluates retrieved policy chunks for contextual relevance.
If relevance is insufficient, executes bounded query expansion/rewriting.
"""

from typing import List, Tuple, Dict, Any
from .state import PolicyChunk

class PolicyGrader:
    def __init__(self, min_relevance_threshold: float = 0.3):
        self.min_relevance_threshold = min_relevance_threshold

    def grade_chunks(self, query: str, chunks: List[PolicyChunk]) -> Tuple[List[PolicyChunk], bool]:
        """
        Grades retrieved chunks.
        Returns: (relevant_chunks, is_sufficient)
        """
        relevant: List[PolicyChunk] = []
        for c in chunks:
            if c.relevance_score >= self.min_relevance_threshold:
                relevant.append(c)

        is_sufficient = len(relevant) > 0
        return relevant, is_sufficient

    def rewrite_query(self, query: str, rewrite_iteration: int, context: Dict[str, Any]) -> str:
        """
        Deterministic bounded query rewriter.
        Expands search terms using domain synonyms based on context.
        """
        product_id = context.get("product_id", "")
        has_low_stock = context.get("low_stock", False)
        missing_fields = context.get("missing_fields", [])

        if rewrite_iteration == 0:
            # First rewrite: expand to core operational policy clauses
            expanded = f"{query} available inventory position calculation reorder point formula safety stock"
            if missing_fields:
                expanded += " missing lead time operator ask idempotency"
            return expanded
        elif rewrite_iteration == 1:
            # Second rewrite: expand to lot sizing, MOQ, and ceiling rules
            expanded = f"{query} supplier minimum order quantity MOQ pack size ceiling rounding unconfirmed stock rules"
            return expanded
        else:
            # Bounded limit reached: return best expanded query
            return f"{query} corporate inventory replenishment and reorder policy sections"
