import sys
from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base
from core.migrator import sync_schema
from models.tables import Incident, ChatHistory, WeeklyReport

def test_migration():
    print("Running migrator...")
    try:
        sync_schema(engine, Base.metadata)
        print("Migration complete.")
    except Exception as e:
        print(f"Migration failed: {e}")
        sys.exit(1)

    print("Verifying models...")
    db = SessionLocal()
    try:
        # Querying Incident checking new columns
        i = db.query(Incident).first()
        if i:
            _ = i.process_name
            _ = i.risk_score
            _ = i.reasons
            
        # Querying ChatHistory checking new columns
        c = db.query(ChatHistory).first()
        if c:
            _ = c.intent
            
        # Querying new table
        w = db.query(WeeklyReport).first()
        
        print("Queries executed successfully without OperationalError!")
    except Exception as e:
        print(f"Endpoint test failed: {e}")
        sys.exit(1)
    finally:
        db.close()
        
    print("All tests passed.")

if __name__ == "__main__":
    test_migration()
