#!/usr/bin/env python3
"""Seed Postgres with transaction CSVs on first run."""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.db.database import SessionLocal, TransactionScore, init_db

DATA_DIR = Path(settings.data_dir)


def seed():
    init_db()
    db = SessionLocal()
    existing = db.query(TransactionScore).count()
    if existing > 0:
        print(f"Database already has {existing} rows — skipping seed.")
        db.close()
        return

    path = DATA_DIR / "transactions_full_with_labels_v2.csv"
    df = pd.read_csv(path, parse_dates=["timestamp"])
    print(f"Seeding {len(df)} transactions from {path.name}...")
    for _, row in df.iterrows():
        db.add(
            TransactionScore(
                transaction_id=row["transaction_id"],
                timestamp=row["timestamp"],
                user_id=row["user_id"],
                device_id=row["device_id"],
                ip_address=row["ip_address"],
                amount_inr=float(row["amount_inr"]),
                payment_method=row["payment_method"],
                merchant_category=row["merchant_category"],
                shipping_city=row["shipping_city"],
                shipping_address_id=row["shipping_address_id"],
                is_fraud=int(row["is_fraud"]),
                cluster_type=row["cluster_type"],
            )
        )
    db.commit()
    db.close()
    print("Seed complete.")


if __name__ == "__main__":
    seed()
