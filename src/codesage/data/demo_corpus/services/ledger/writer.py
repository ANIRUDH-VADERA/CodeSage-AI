"""Consumes posting events from Kafka and writes them to Postgres."""
from .settings import BATCH_SIZE


class LedgerWriter:
    """Writes a batch, then commits Kafka offsets. Committing first would lose messages on a crash (INC-1002)."""

    def __init__(self, consumer, db):
        self.consumer = consumer
        self.db = db

    def run_once(self):
        batch = self.consumer.poll(max_records=BATCH_SIZE)
        if not batch:
            return 0
        self.write_batch(batch)
        self.consumer.commit()
        return len(batch)

    def write_batch(self, events):
        # COPY into an UNLOGGED staging table skips WAL for the bulk load; one upsert moves rows to the target.
        with self.db.transaction() as tx:
            tx.copy_rows("staging_postings", events)
            tx.execute("INSERT INTO postings SELECT * FROM staging_postings ON CONFLICT (event_id) DO NOTHING")
            tx.execute("TRUNCATE staging_postings")
