import os
from pathlib import Path
from dotenv import load_dotenv
import sqlalchemy as sa
import pandas as pd
from google.cloud import bigquery
from db_connector import get_postgres_engine

# Dynamically locate and load the .env file from the local root workspace
env_path = Path(__file__).resolve().parent / '.env'
load_dotenv(dotenv_path=env_path)

def run_elt_migration():
    print("Connecting to source (PostgreSQL) and initializing BigQuery Client...")
    pg_engine = get_postgres_engine()
    
    project_id = os.getenv("GBQ_PROJECT_ID")
    dataset_id = os.getenv("GBQ_DATASET_ID")
    if dataset_id and "." in dataset_id:
        dataset_id = dataset_id.split(".")[-1]
    
    # Initialize the official cloud-native BigQuery client
    # It automatically reads GOOGLE_APPLICATION_CREDENTIALS from your .env
    bq_client = bigquery.Client(project=project_id)
    
    tables_to_migrate = [
        'dimcurrency', 'dimcustomer', 'dimdate', 'dimemployee', 
        'dimgeography', 'dimproduct', 'dimproductcategory', 
        'dimproductsubcategory', 'dimpromotion', 'dimreseller', 
        'dimsalesterritory', 'factinternetsales', 'factresellersales'
    ]
    
    print("\nStarting cloud-native database migration to Hong Kong (asia-east2)...")
    
    successful_tables = []
    failed_tables = []
    
    for table_name in tables_to_migrate:
        try:
            print(f"Processing table: {table_name}...")
            
            # 1. Fetch data from local PostgreSQL
            with pg_engine.connect() as pg_conn:
                query = sa.text(f"SELECT * FROM public.{table_name}")
                query_result = pg_conn.execute(query).fetchall()
                records = [dict(row._mapping) for row in query_result]
            
            if records:
                df = pd.DataFrame(records)
                
                # Convert Decimals to float to avoid JSON serialization bugs
                for col in df.columns:
                    if df[col].apply(lambda x: x.__class__.__name__ == 'Decimal').any():
                        df[col] = df[col].astype(float)
                
                # 2. Define the explicit BigQuery target path
                table_ref = f"{project_id}.{dataset_id}.{table_name}"
                
                # 3. Configure a native upload load job
                # WRITE_TRUNCATE behaves exactly like if_exists='replace'
                job_config = bigquery.LoadJobConfig(
                    write_disposition="WRITE_TRUNCATE",
                )
                
                print(f"  -> Streaming {len(records)} rows directly to BigQuery via cloud APIs...")
                # Stream the dataframe natively up to the Hong Kong region node
                # This completely isolates the transfer from SQLAlchemy dialect checks!
                job = bq_client.load_table_from_dataframe(
                    df, table_ref, job_config=job_config, location="asia-east2"
                )
                job.result()  # Wait for the cloud load job to finish executing
                
                print(f"  ✅ Success: {table_name} is fully loaded to BigQuery!\n")
                successful_tables.append(table_name)
            else:
                print(f"  ⚠️ Skipping {table_name}: Table is empty.\n")
                
        except Exception as e:
            print(f"  ❌ Error migrating table {table_name}: {str(e)}\n")
            failed_tables.append((table_name, str(e)))
            continue

    print(f"Migration Summary: {len(successful_tables)}/{len(tables_to_migrate)} tables successfully migrated.")
    if failed_tables:
        print(f"❌ Failed tables: {[t[0] for t in failed_tables]}")
        raise SystemExit(1)

if __name__ == "__main__":
    run_elt_migration()
