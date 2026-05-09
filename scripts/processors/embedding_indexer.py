#!/usr/bin/env python3
"""
Embedding Indexer

Loads NPS content from the database, chunks text, generates embeddings
via Ollama, and writes them to the content_embeddings table for
semantic search.

Usage:
    # Index all content
    python scripts/processors/embedding_indexer.py

    # Force rebuild all embeddings
    python scripts/processors/embedding_indexer.py --force-refresh

    # Custom batch size
    python scripts/processors/embedding_indexer.py --batch-size 25
"""

from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import Engine, text

# Add project root to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from config.settings import config
from scripts.database.db_writer import DatabaseWriter, get_postgres_engine
from scripts.processors.text_chunker import (
    chunk_park_description,
    chunk_places,
    chunk_thingstodo,
)
from utils.embedding_client import get_embeddings_sync
from utils.exceptions import NpsHikesError
from utils.logging import setup_embedding_indexer_logging


class EmbeddingIndexer:
    """Load content, chunk text, generate embeddings, and write to DB."""

    def __init__(
        self,
        log_level: str | None = None,
        engine: Engine | None = None,
        batch_size: int | None = None,
    ) -> None:
        """Initialize the embedding indexer.

        Args:
            log_level: Logging level override.
            engine: SQLAlchemy engine. If None, creates one.
            batch_size: Number of texts to embed in a single Ollama call.
        """
        self.logger = setup_embedding_indexer_logging(log_level)
        self.engine = engine or get_postgres_engine()
        self.db_writer = DatabaseWriter(self.engine, self.logger)
        self.batch_size = batch_size or config.EMBEDDING_BATCH_SIZE

    def load_content_from_db(self) -> list[dict]:
        """Load thingstodo, places, and park descriptions from the database.

        Returns:
            List of content records as dicts, each with a 'content_type'
            key indicating the source table.
        """
        records: list[dict] = []

        with self.engine.connect() as conn:
            # Load thingstodo
            result = conn.execute(
                text("""
                SELECT id, park_code, title, short_description,
                       long_description, activities, topics, tags,
                       season, duration
                FROM nps_thingstodo
            """)
            )
            for row in result.fetchall():
                records.append(
                    {
                        "content_type": "thingstodo",
                        "id": row.id,
                        "park_code": row.park_code,
                        "title": row.title,
                        "short_description": row.short_description,
                        "long_description": row.long_description,
                        "activities": row.activities,
                        "topics": row.topics,
                        "tags": row.tags,
                        "season": row.season,
                        "duration": row.duration,
                    }
                )

            # Load places
            result = conn.execute(
                text("""
                SELECT id, park_code, title, short_description,
                       body_text, tags
                FROM nps_places
            """)
            )
            for row in result.fetchall():
                records.append(
                    {
                        "content_type": "places",
                        "id": row.id,
                        "park_code": row.park_code,
                        "title": row.title,
                        "short_description": row.short_description,
                        "body_text": row.body_text,
                        "tags": row.tags,
                    }
                )

            # Load park descriptions
            result = conn.execute(
                text("""
                SELECT park_code, full_name, description
                FROM parks
                WHERE description IS NOT NULL AND description != ''
            """)
            )
            for row in result.fetchall():
                records.append(
                    {
                        "content_type": "park_description",
                        "park_code": row.park_code,
                        "park_name": row.full_name,
                        "description": row.description,
                    }
                )

        self.logger.info(f"Loaded {len(records)} content records from database")
        return records

    def chunk_all_content(self, records: list[dict]) -> list[dict]:
        """Apply chunking to all content records.

        Args:
            records: List of content records from load_content_from_db.

        Returns:
            List of chunk dicts ready for embedding.
        """
        chunks: list[dict] = []

        for record in records:
            content_type = record["content_type"]
            if content_type == "thingstodo":
                chunks.extend(chunk_thingstodo(record))
            elif content_type == "places":
                chunks.extend(chunk_places(record))
            elif content_type == "park_description":
                chunks.extend(
                    chunk_park_description(
                        record["park_code"],
                        record.get("park_name", ""),
                        record.get("description", ""),
                    )
                )

        self.logger.info(
            f"Created {len(chunks)} text chunks from {len(records)} records"
        )
        return chunks

    def embed_chunks(self, chunks: list[dict]) -> list[dict]:
        """Generate embeddings for all chunks in batches.

        Args:
            chunks: List of chunk dicts from chunk_all_content.

        Returns:
            Same chunks with 'embedding' key added.
        """
        total = len(chunks)
        for i in range(0, total, self.batch_size):
            batch = chunks[i : i + self.batch_size]
            texts = [c["chunk_text"] for c in batch]

            embeddings = get_embeddings_sync(texts)

            for chunk, embedding in zip(batch, embeddings, strict=True):
                chunk["embedding"] = embedding

            self.logger.info(
                f"Embedded batch {i // self.batch_size + 1}/"
                f"{(total + self.batch_size - 1) // self.batch_size} "
                f"({min(i + self.batch_size, total)}/{total} chunks)"
            )

        return chunks

    def write_embeddings_to_db(self, chunks: list[dict]) -> None:
        """Write embedded chunks to the content_embeddings table.

        Args:
            chunks: List of chunk dicts with 'embedding' key.
        """
        self.db_writer.write_embeddings(chunks)

    def index_all(self, force_refresh: bool = False) -> None:
        """Run the full indexing pipeline: load -> chunk -> embed -> write.

        Args:
            force_refresh: Accepted for CLI compatibility (embeddings are
                always rebuilt from scratch to prevent duplicates).
        """
        # Always truncate before re-indexing to prevent duplicates.
        # The indexer reprocesses all content each run, so stale rows
        # would accumulate without this.
        self.logger.info("Clearing existing embeddings before re-indexing")
        self.db_writer.truncate_tables(["content_embeddings"])

        records = self.load_content_from_db()
        if not records:
            self.logger.warning("No content records found in database")
            return

        chunks = self.chunk_all_content(records)
        if not chunks:
            self.logger.warning("No chunks generated from content")
            return

        chunks = self.embed_chunks(chunks)
        self.write_embeddings_to_db(chunks)

        self.logger.info(
            f"Indexing complete: {len(chunks)} embeddings written to database"
        )


def main() -> int:
    """Main entry point for the embedding indexer.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    parser = argparse.ArgumentParser(
        description="Generate and store embeddings for NPS content",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Clear and rebuild all embeddings",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=config.EMBEDDING_BATCH_SIZE,
        metavar="N",
        help=f"Embedding batch size (default: {config.EMBEDDING_BATCH_SIZE})",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity",
    )
    parser.add_argument(
        "--write-db",
        action="store_true",
        help="Accepted for orchestrator compatibility (always writes to DB)",
    )

    args = parser.parse_args()

    try:
        config.validate_for_database_operations()

        indexer = EmbeddingIndexer(
            log_level=args.log_level,
            batch_size=args.batch_size,
        )
        indexer.index_all(force_refresh=args.force_refresh)
        return 0

    except NpsHikesError as e:
        print(f"Error: {e!s}")
        if e.context:
            print(f"Context: {e.context}")
        return 1
    except KeyboardInterrupt:
        print("\nIndexing interrupted by user")
        return 1
    except Exception as e:
        print(f"Unexpected error: {e!s}")
        return 1


if __name__ == "__main__":
    exit(main())
