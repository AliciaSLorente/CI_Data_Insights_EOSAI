#!/usr/bin/env python
"""Quick script to extract PDF fields and save to CSV."""

from pathlib import Path
from src.data.pdf_parser import parse_all_companies
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

data_root = Path(r'C:\Users\A.SANCHEZLORENTE\Zurich Insurance\Hyper Challenge 2026 - 04 - Leveraging historical data for new customers\Use Case Data')

print(f"Parsing company folders from: {data_root}\n")
df = parse_all_companies(data_root)

output_path = Path('data/parsed/pdf_extracted_fields.csv')
output_path.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(output_path, index=False)

print(f"\n✅ [DONE] Extracted {len(df)} PDF submissions")
print(f"📊 Columns: {len(df.columns)}")
print(f"💾 Saved to: {output_path}")

print(f"\n📈 EXTRACTION SUMMARY:")
print(f"  Total PDFs: {len(df)}")
print(f"  Successful: {df['extraction_success'].sum()}")
print(f"  Failed: {(~df['extraction_success']).sum()}")
print(f"  Revenue found: {df['revenue_millions'].notna().sum()} ({df['revenue_millions'].notna().sum()/len(df)*100:.1f}%)")
print(f"  Employees found: {df['employee_count'].notna().sum()} ({df['employee_count'].notna().sum()/len(df)*100:.1f}%)")

control_cols = [c for c in df.columns if c.startswith('control_')]
print(f"\n🔐 CONTROL ADOPTION (top 6):")
for col in sorted(control_cols)[:6]:
    rate = df[col].sum() / len(df) * 100
    control_name = col.replace('control_', '').replace('_', ' ').title()
    print(f"  {control_name}: {rate:.1f}%")

print("\n✅ PDF extraction complete!")
