#!/usr/bin/env python3
"""
Content-Trail Linker

Pre-computes mappings between NPS content embeddings and trail records.
For each content_embedding with source_type in ('thingstodo', 'places'),
this script matches the content title against trail names in the same park
using fuzzy name matching (reusing patterns from trail_matcher.py).

The resulting content_trail_mapping table enables semantic search results
to be joined back to structured trail data.

Usage:
    python scripts/processors/content_trail_linker.py --write-db
    python scripts/processors/content_trail_linker.py --write-db --log-level DEBUG
"""

from __future__ import annotations

import argparse
import difflib
import logging
import os
import sys

import pandas as pd
from sqlalchemy import Engine
from sqlalchemy import text as sa_text

# Add project root to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from config.settings import config
from scripts.database.db_writer import DatabaseWriter, get_postgres_engine
from utils.exceptions import NpsHikesError
from utils.logging import setup_content_trail_linker_logging

# Leading verbs to strip from content titles before matching
LEADING_VERBS = [
    "hike",
    "explore",
    "visit",
    "walk",
    "discover",
    "experience",
    "enjoy",
    "try",
    "take",
    "go",
    "ride",
    "bike",
    "climb",
]

# Words to strip during name preprocessing (same as trail_matcher.py)
# Ordered longest-first to avoid partial replacements (e.g. "trailhead" before "trail")
TRAIL_WORDS_TO_REMOVE = [
    "trailhead",
    "trails",
    "trail",
    "paths",
    "path",
    "walks",
    "walk",
]


def strip_leading_verb(title: str) -> str:
    """Strip leading verbs from a content title.

    Args:
        title: Original content title (e.g. "Hike the Mist Trail to Vernal Fall").

    Returns:
        Title with the leading verb removed.
    """
    if not title:
        return ""

    words = title.split()
    if not words:
        return ""

    if words[0].lower() in LEADING_VERBS:
        words = words[1:]

    # Also strip leading articles after verb removal
    if words and words[0].lower() in ("the", "a", "an"):
        words = words[1:]

    return " ".join(words)


def preprocess_name(name: str) -> str:
    """Preprocess a name for matching.

    Reuses the same logic as TrailMatcher.preprocess_name() from trail_matcher.py:
    lowercase, strip trail/trailhead/path/walk words, remove punctuation,
    normalize whitespace.

    Args:
        name: Original name.

    Returns:
        Preprocessed name.
    """
    if not name:
        return ""

    processed = name.lower().strip()

    for word in TRAIL_WORDS_TO_REMOVE:
        processed = processed.replace(word, "")

    # Remove extra whitespace and punctuation
    processed = " ".join(processed.split())
    processed = processed.replace(",", "").replace(".", "").replace("-", " ")

    return processed.strip()


def preprocess_content_title(title: str) -> str:
    """Full preprocessing pipeline for content titles.

    Combines verb stripping with name preprocessing.

    Args:
        title: Original content title.

    Returns:
        Fully preprocessed title ready for matching.
    """
    if not title:
        return ""

    stripped = strip_leading_verb(title)
    return preprocess_name(stripped)


def calculate_name_similarity(name1: str, name2: str) -> float:
    """Calculate similarity between two names with containment boost.

    Reuses the same pattern as TrailMatcher.calculate_name_similarity()
    from trail_matcher.py: SequenceMatcher ratio with containment boost.

    Args:
        name1: First preprocessed name.
        name2: Second preprocessed name.

    Returns:
        Similarity score between 0 and 1.
    """
    if not name1 or not name2:
        return 0.0

    processed1 = preprocess_name(name1)
    processed2 = preprocess_name(name2)

    if not processed1 or not processed2:
        return 0.0

    similarity = difflib.SequenceMatcher(None, processed1, processed2).ratio()

    # Boost score for partial matches (one name contains the other)
    if processed1 in processed2 or processed2 in processed1:
        similarity = max(similarity, 0.8)

    return similarity


class ContentTrailLinker:
    """Link content embeddings to trail records via fuzzy name matching."""

    def __init__(
        self,
        write_db: bool = False,
        logger: logging.Logger | None = None,
        engine: Engine | None = None,
    ) -> None:
        """Initialize the content-trail linker.

        Args:
            write_db: Whether to write results to the database.
            logger: Logger instance.
            engine: SQLAlchemy engine. If None, creates one.
        """
        self.logger = logger or logging.getLogger("content_trail_linker")
        self.engine = engine or get_postgres_engine()
        self.db_writer = DatabaseWriter(self.engine, self.logger) if write_db else None
        self.threshold = config.CONTENT_TRAIL_LINKING_THRESHOLD

        # Statistics
        self.stats = {
            "total_embeddings": 0,
            "matched_tnm": 0,
            "matched_osm": 0,
            "no_match": 0,
        }

    def load_content_embeddings(self) -> pd.DataFrame:
        """Load content embeddings with source_type in ('thingstodo', 'places').

        Returns:
            DataFrame with columns: id, park_code, title, source_type.
        """
        query = """
        SELECT id, park_code, title, source_type
        FROM content_embeddings
        WHERE source_type IN ('thingstodo', 'places')
          AND title IS NOT NULL
          AND title != ''
        ORDER BY park_code, id
        """
        df = pd.read_sql(query, self.engine)
        self.logger.info(
            f"Loaded {len(df)} content embeddings for linking "
            f"({df['park_code'].nunique()} parks)"
        )
        return df

    def load_trails_for_park(self, park_code: str) -> list[dict]:
        """Load all trail names for a park (TNM first, then OSM).

        Args:
            park_code: 4-character park code.

        Returns:
            List of dicts with keys: trail_name, trail_id, source.
        """
        trails: list[dict] = []

        # Load TNM trails first (preferred source)
        try:
            tnm_query = sa_text("""
            SELECT permanent_identifier AS trail_id, name AS trail_name
            FROM tnm_hikes
            WHERE park_code = :park_code
              AND name IS NOT NULL
              AND name != ''
            """)
            tnm_df = pd.read_sql(
                tnm_query, self.engine, params={"park_code": park_code}
            )
            for _, row in tnm_df.iterrows():
                trails.append(
                    {
                        "trail_name": row["trail_name"],
                        "trail_id": str(row["trail_id"]),
                        "source": "TNM",
                    }
                )
        except Exception as e:
            self.logger.warning(f"Error loading TNM trails for {park_code}: {e}")

        # Load OSM trails
        try:
            osm_query = sa_text("""
            SELECT osm_id::text AS trail_id, name AS trail_name
            FROM osm_hikes
            WHERE park_code = :park_code
              AND name IS NOT NULL
              AND name != ''
            """)
            osm_df = pd.read_sql(
                osm_query, self.engine, params={"park_code": park_code}
            )
            for _, row in osm_df.iterrows():
                trails.append(
                    {
                        "trail_name": row["trail_name"],
                        "trail_id": str(row["trail_id"]),
                        "source": "OSM",
                    }
                )
        except Exception as e:
            self.logger.warning(f"Error loading OSM trails for {park_code}: {e}")

        return trails

    def find_best_match(self, content_title: str, trails: list[dict]) -> dict | None:
        """Find the best trail match for a content title.

        TNM trails are preferred over OSM when both match equally well.

        Args:
            content_title: Original content title.
            trails: List of trail dicts from load_trails_for_park().

        Returns:
            Best match dict with trail info and scores, or None if below threshold.
        """
        if not content_title or not trails:
            return None

        preprocessed_title = preprocess_content_title(content_title)
        if not preprocessed_title:
            return None

        best_match = None
        best_score = 0.0

        for trail in trails:
            score = calculate_name_similarity(preprocessed_title, trail["trail_name"])

            # Prefer TNM over OSM when scores are equal
            if score > best_score or (
                score == best_score
                and best_match is not None
                and trail["source"] == "TNM"
                and best_match["trail_source"] == "OSM"
            ):
                best_score = score
                best_match = {
                    "trail_name": trail["trail_name"],
                    "trail_id": trail["trail_id"],
                    "trail_source": trail["source"],
                    "name_similarity_score": score,
                    "match_confidence": score,
                }

        if best_match and best_score >= self.threshold:
            return best_match

        return None

    def run_linking(self) -> None:
        """Run the complete content-trail linking process."""
        self.logger.info("Starting content-trail linking process...")

        # Load content embeddings
        embeddings_df = self.load_content_embeddings()
        if embeddings_df.empty:
            self.logger.warning("No content embeddings found for linking")
            return

        self.stats["total_embeddings"] = len(embeddings_df)

        # Process by park for efficiency (load trails once per park)
        mappings: list[dict] = []
        parks = embeddings_df["park_code"].unique()

        for park_code in parks:
            park_embeddings = embeddings_df[embeddings_df["park_code"] == park_code]
            trails = self.load_trails_for_park(park_code)

            if not trails:
                self.stats["no_match"] += len(park_embeddings)
                self.logger.debug(f"No trails found for park {park_code}, skipping")
                continue

            for _, emb in park_embeddings.iterrows():
                match = self.find_best_match(emb["title"], trails)

                if match:
                    mappings.append(
                        {
                            "content_embedding_id": emb["id"],
                            "park_code": park_code,
                            "trail_name": match["trail_name"],
                            "trail_source": match["trail_source"],
                            "trail_id": match["trail_id"],
                            "content_title": emb["title"],
                            "name_similarity_score": match["name_similarity_score"],
                            "match_confidence": match["match_confidence"],
                        }
                    )
                    if match["trail_source"] == "TNM":
                        self.stats["matched_tnm"] += 1
                    else:
                        self.stats["matched_osm"] += 1
                else:
                    self.stats["no_match"] += 1

        self.logger.info(f"Generated {len(mappings)} content-trail mappings")

        # Write to database
        if self.db_writer and mappings:
            self._write_mappings(mappings)

        self._print_summary()

    def _write_mappings(self, mappings: list[dict]) -> None:
        """Write content-trail mappings to the database.

        Truncates existing mappings and writes fresh data.

        Args:
            mappings: List of mapping dicts to write.
        """
        self.logger.info("Writing content-trail mappings to database...")

        try:
            # Truncate existing mappings
            with self.engine.begin() as conn:
                conn.execute(
                    sa_text(
                        "TRUNCATE TABLE content_trail_mapping RESTART IDENTITY CASCADE"
                    )
                )

            # Write new mappings
            df = pd.DataFrame(mappings)
            df.to_sql(
                "content_trail_mapping",
                self.engine,
                if_exists="append",
                index=False,
            )
            self.logger.info(f"Wrote {len(mappings)} mappings to content_trail_mapping")
        except Exception as e:
            self.logger.error(f"Failed to write mappings: {e}")
            raise

    def _print_summary(self) -> None:
        """Print linking summary."""
        total = self.stats["total_embeddings"]
        matched = self.stats["matched_tnm"] + self.stats["matched_osm"]
        match_rate = (matched / total * 100) if total > 0 else 0

        self.logger.info("=" * 60)
        self.logger.info("CONTENT-TRAIL LINKING SUMMARY")
        self.logger.info("=" * 60)
        self.logger.info(f"Total embeddings processed: {total}")
        self.logger.info(f"Matched to TNM trails: {self.stats['matched_tnm']}")
        self.logger.info(f"Matched to OSM trails: {self.stats['matched_osm']}")
        self.logger.info(f"No match found: {self.stats['no_match']}")
        self.logger.info(f"Match rate: {match_rate:.1f}%")
        self.logger.info("=" * 60)


def main() -> int:
    """Main entry point for the content-trail linker.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    parser = argparse.ArgumentParser(
        description="Link NPS content embeddings to trail records",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --write-db                   # Link content to trails and write to DB
  %(prog)s --write-db --log-level DEBUG # With debug logging
        """,
    )
    parser.add_argument(
        "--write-db",
        action="store_true",
        help="Write results to database",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Set logging level",
    )

    args = parser.parse_args()

    logger = setup_content_trail_linker_logging(log_level=args.log_level)

    try:
        config.validate_for_database_operations()

        linker = ContentTrailLinker(
            write_db=args.write_db,
            logger=logger,
        )
        linker.run_linking()

        logger.info("Content-trail linking completed successfully")
        return 0

    except NpsHikesError as e:
        logger.error(f"Content-trail linking failed: {e}")
        if e.context:
            logger.error(f"Context: {e.context}")
        return 1
    except Exception as e:
        logger.error(f"Content-trail linking failed with unexpected error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
