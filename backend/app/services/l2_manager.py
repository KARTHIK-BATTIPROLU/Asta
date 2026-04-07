import logging
import asyncio
import spacy
import pytextrank
import numpy as np
from datetime import datetime, timezone
from transformers import pipeline
from backend.app.db.mongo import MongoDB

logger = logging.getLogger("L2_Semantic_RAG")

class L2MemoryManager:
    def __init__(self):
        self.collection_name = "session_memory"
        
        self.nlp = None
        self.summarizer = None
        self.embedder = None
        self._load_models()

    def _load_models(self):
        try:
            logger.info("[L2_RAG] Loading Extractive spaCy Core...")
            self.nlp = spacy.load("en_core_web_sm")
            self.nlp.add_pipe("textrank")
            
            logger.info("[L2_RAG] Loading Abstractive BART (Heavyweight CPU Matrix)...")
            self.summarizer = pipeline("summarization", model="facebook/bart-large-cnn")
            
            logger.info("[L2_RAG] Boot Sequence Complete (embedding via shared EmbeddingService).")
        except Exception as e:
            logger.error(f"[L2_RAG] Failed to initialize Machine Learning models. Missing python -m spacy download en_core_web_sm?: {e}")

    @property
    def collection(self):
        return MongoDB.db[self.collection_name] if MongoDB.db is not None else None

    def _extractive_distillation(self, raw_text: str) -> str:
        """Stage 1: Filters math sentences using TextRank"""
        if not self.nlp:
            return raw_text
        doc = self.nlp(raw_text)
        # Pull top 3 ranked sentences based on TextRank math
        ranked_sentences = [sent.text for sent in doc._.textrank.summary(limit_phrases=15, limit_sentences=3)]
        return " ".join(ranked_sentences)

    def _abstractive_summarization(self, text: str) -> str:
        """Stage 2: Translates filtered text into fluent abstractive summarization using BART"""
        if not self.summarizer:
            return text
        try:
            out = self.summarizer(text, max_length=60, min_length=15, do_sample=False)
            return out[0]['summary_text']
        except Exception as e:
            logger.error(f"[L2_RAG] BART Summarizer failed natively: {e}")
            return text

    def _generate_dense_vector(self, text: str) -> list[float]:
        """Maps output directly to strict 384-dimensional native float array.
        Uses the shared EmbeddingService from the registry to avoid duplicate model loading."""
        try:
            from backend.app.core.registry import registry
            embedding_service = registry.get("embedding")
            if embedding_service:
                return embedding_service.embed(text)
        except Exception:
            pass
        # Fallback: if registry not yet initialized (e.g. during early boot)
        if self.embedder:
            return self.embedder.encode(text).tolist()
        return []

    def sync_process_and_store(self, session_id: str, raw_segment: str) -> str:
        """Standard CPU bounded ML inferencing layer executing dense RAG pipelines.
        Returns the generated summary text for downstream L3 processing."""
        logger.info(f"[L2_RAG] Executing Dual-Stage Extractive/Abstractive Summarization.")
        
        # Pipelines execution
        distilled_text = self._extractive_distillation(raw_segment)
        # Edge case handler if extraction string matches too perfectly small
        if len(distilled_text.split()) < 15:
            summary = distilled_text
        else:
            summary = self._abstractive_summarization(distilled_text)
        
        vector = self._generate_dense_vector(summary)
        
        doc = {
            "session_id": session_id,
            "raw_segment_ref": [raw_segment],
            "summary": summary,
            "embedding": vector,
            "created_at": datetime.now(timezone.utc)
        }
        
        if self.collection is not None:
             # Upsert to prevent duplicate session_memory documents per session
             self.collection.update_one(
                 {"session_id": session_id},
                 {"$set": doc},
                 upsert=True
             )
             logger.info(f"[L2_RAG] Memory embedded efficiently dynamically to DB for {session_id}")

        return summary

    async def auto_summarize_and_store(self, session_id: str, raw_segment: str):
        """Asynchronous API entry point wrapping PyTorch in thread worker pooling.
        NOTE: L3 Graph updates are handled by the MemoryOrchestrator, not here."""
        if not raw_segment or len(raw_segment.strip()) < 10:
             return
        await asyncio.to_thread(self.sync_process_and_store, session_id, raw_segment)

    def sync_query(self, query_text: str, top_k: int = 3) -> list[str]:
         query_vector = self._generate_dense_vector(query_text)
         if not query_vector or self.collection is None:
             return []
             
         try:
             cursor = self.collection.find({}, {"summary": 1, "embedding": 1})
             memories = list(cursor)
             
             scored_memories = []
             q_arr = np.array(query_vector)
             q_norm = np.linalg.norm(q_arr)
             
             if q_norm == 0:
                 return []
                 
             for mem in memories:
                 emb = mem.get("embedding")
                 if not emb or len(emb) == 0: continue
                 
                 emb_arr = np.array(emb)
                 mem_norm = np.linalg.norm(emb_arr)
                 
                 if mem_norm == 0: continue
                 
                 sim = np.dot(q_arr, emb_arr) / (q_norm * mem_norm)
                 scored_memories.append((sim, mem.get("summary", "")))
                 
             filtered = [m for m in scored_memories if m[0] >= 0.1]
             filtered.sort(key=lambda x: x[0], reverse=True)
             
             return [m[1] for m in filtered[:top_k]]
             
         except Exception as e:
             logger.error(f"[L2_RAG] RAG Numpy calculation failure: {e}")
             return []

    async def query_memory(self, query_text: str, top_k: int = 3) -> list[str]:
         """Asynchronous search wrapping Numpy $O(N)$ execution outside the main Uvicorn pipe."""
         return await asyncio.to_thread(self.sync_query, query_text, top_k)

l2_manager = L2MemoryManager()
