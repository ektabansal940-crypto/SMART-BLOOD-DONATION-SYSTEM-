"""
Database Migration Script: Add user_id to Transaction table

This script adds the user_id column to the Transaction table.
Run this once after updating the models.

Usage:
    python migrate_add_user_id.py
"""

from app import app, db, Transaction
from sqlalchemy import text

def migrate():
    with app.app_context():
        try:
            # Check if column already exists
            result = db.session.execute(text(
                'PRAGMA table_info("transaction")'
            )).fetchall()
            
            columns = [row[1] for row in result]
            
            if 'user_id' not in columns:
                print("[MIGRATION] Adding user_id column to transaction table...")
                
                # Add the column (SQLite allows NULL for existing rows)
                db.session.execute(text(
                    'ALTER TABLE "transaction" ADD COLUMN user_id INTEGER'
                ))
                
                # Add foreign key constraint (note: SQLite has limited ALTER TABLE support)
                # The foreign key is defined in the model but won't be enforced on existing data
                
                db.session.commit()
                print("[MIGRATION] ✓ Successfully added user_id column")
                print("[MIGRATION] Note: Existing transactions will have user_id = NULL")
                print("[MIGRATION] New transactions will automatically track the creating user")
            else:
                print("[MIGRATION] ✓ user_id column already exists, no migration needed")
                
        except Exception as e:
            print(f"[MIGRATION] ✗ Error during migration: {e}")
            db.session.rollback()
            raise

if __name__ == "__main__":
    print("="*60)
    print("Database Migration: Add user_id to Transaction")
    print("="*60)
    migrate()
    print("="*60)
    print("Migration complete!")
    print("="*60)
