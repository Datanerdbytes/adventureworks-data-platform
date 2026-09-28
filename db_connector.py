import os
from pathlib import Path
from dotenv import load_dotenv
import sqlalchemy as sa
from sqlalchemy.engine import Engine

# Dynamically locate and load the .env file from the local root workspace
env_path = Path(__file__).resolve().parent / '.env'
load_dotenv(dotenv_path=env_path)

def get_postgres_engine() -> Engine:
    """
    Creates and returns a reusable SQLAlchemy engine pointing to the source 
    PostgreSQL instance containing your migrated AdventureWorks dataset.
    """
    try:
        host = os.getenv("PG_HOST")
        port = os.getenv("PG_PORT")
        db = os.getenv("PG_DB")
        user = os.getenv("PG_USER")
        password = os.getenv("PG_PASSWORD")
        
        # Construct standard postgresql+psycopg2 URL structure
        connection_url = sa.URL.create(
            "postgresql+psycopg2",
            username=user,
            password=password,
            host=host,
            port=port,
            database=db
        )
        
        # Initialize engine configuration instance
        engine = sa.create_engine(connection_url, echo=False)
        return engine
        
    except Exception as e:
        raise ConnectionError(f"Failed to generate PostgreSQL Engine: {str(e)}")

def get_bigquery_engine() -> Engine:
    try:
        project_id = os.getenv("GBQ_PROJECT_ID")
        dataset_id = os.getenv("GBQ_DATASET_ID")
        if dataset_id and "." in dataset_id:
            dataset_id = dataset_id.split(".")[-1]
        
        if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            raise ValueError("GOOGLE_APPLICATION_CREDENTIALS path variable is missing.")
            
        # Clean target: bigquery://quantum-echo-data-eng-prod/raw_adventureworks
        bigquery_url = f"bigquery://{project_id}/{dataset_id}"
        
        engine = sa.create_engine(bigquery_url, location="asia-east2")
        return engine
        
    except Exception as e:
        raise ConnectionError(f"Failed to generate BigQuery Engine: {str(e)}")

# ==============================================================================
# Execution Sandbox: Verifies active connectivity
# ==============================================================================
if __name__ == "__main__":
    print("Testing connection engine initializations...")
    
    source_engine = get_postgres_engine()
    with source_engine.connect() as conn:
        result = conn.execute(sa.text("SELECT version();")).fetchone()
        print(f"✅ PostgreSQL Connected successfully!\nVersion: {result[0]}\n")
        
    print("🚀 Ready for Step 2 (Database Reflection Engine Development)!")
