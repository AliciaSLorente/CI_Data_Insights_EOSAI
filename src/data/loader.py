"""
Data loader: Ingest Excel (Dataset 1) and PDFs (Dataset 2).
"""

import pandas as pd
from pathlib import Path
import sqlite3
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class DataLoader:
    def __init__(self, db_path: str = "data/parsed/cache.db"):
        self.db_path = db_path
        self.conn = None
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite cache."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        logger.info(f"Initialized SQLite cache at {self.db_path}")
    
    def load_excel_submissions(self, file_path: str) -> pd.DataFrame:
        """
        Load Dataset 1 (Excel) with all Specialties submissions.
        Expected columns: Company, Effective Date, NAICS, SIC, Product, Broker, Status, Quoted Premium
        """
        df = pd.read_excel(file_path)
        logger.info(f"Loaded {len(df)} submissions from {file_path}")
        
        # Store in cache
        df.to_sql("submissions_raw", self.conn, if_exists="replace", index=False)
        return df
    
    def identify_repeats(self) -> pd.DataFrame:
        """
        Query: Which customers appear >1 time?
        Returns DataFrame with customer, count, LOBs.
        """
        query = """
        SELECT 
            Company,
            COUNT(*) as submission_count,
            GROUP_CONCAT(DISTINCT Product) as products,
            GROUP_CONCAT(DISTINCT Broker) as brokers
        FROM submissions_raw
        GROUP BY Company
        HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC
        """
        repeats = pd.read_sql(query, self.conn)
        logger.info(f"Found {len(repeats)} repeat customers")
        return repeats
    
    def load_pdf_submissions(self, folder_path: str) -> dict:
        """
        Load Dataset 2 (PDFs) from folder structure.
        Expected: folder_path/Customer_001/submission_2022.pdf, submission_2024.pdf, etc.
        
        Returns dict: {customer_id: [list of pdf paths]}
        """
        # Placeholder: scan folder and return PDF paths
        customer_pdfs = {}
        for customer_folder in Path(folder_path).iterdir():
            if customer_folder.is_dir():
                pdfs = list(customer_folder.glob("*.pdf"))
                if pdfs:
                    customer_pdfs[customer_folder.name] = pdfs
        
        logger.info(f"Found {len(customer_pdfs)} customer folders with PDFs")
        return customer_pdfs
    
    def close(self):
        if self.conn:
            self.conn.close()


# Usage example
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    loader = DataLoader()
    
    # Load Dataset 1
    # df = loader.load_excel_submissions("data/raw/Dataset1.xlsx")
    # repeats = loader.identify_repeats()
    # print(repeats.head())
    
    # Load Dataset 2
    # pdfs = loader.load_pdf_submissions("data/raw/Dataset2_PDFs")
    # print(f"Loaded {len(pdfs)} customers with PDFs")
    
    loader.close()
