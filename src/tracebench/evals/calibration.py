"""Human labels and judge calibration.

The labeling sample is about half of each task category in a run, picked at
random with a fixed seed, so it's fair (not hand-picked) and repeatable.
"""

import math
import random
from collections import defaultdict

from sqlalchemy import text

from tracebench.db import engine

SAMPLE_SEED = 7
SAMPLE_FRACTION = 0.5


def label_sample(run_id: int) -> list[int]:
    """Result IDs to label: about half of each task category, chosen with a fixed seed."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT r.id, t.category
            FROM evals.results AS r
            JOIN evals.tasks AS t
              ON t.id = r.task_id AND t.dataset_version = r.dataset_version
            WHERE r.run_id = :run_id
            ORDER BY r.id
        """), {"run_id": run_id}).mappings().all()

    by_category: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        by_category[row["category"]].append(row["id"])

    rng = random.Random(SAMPLE_SEED)
    chosen = []
    for category in sorted(by_category):
        ids = by_category[category]
        chosen.extend(rng.sample(ids, math.ceil(len(ids) * SAMPLE_FRACTION)))
    return sorted(chosen)