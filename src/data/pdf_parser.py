"""
PDF Parser for Zurich Hackathon — Extract fields from company submission PDFs.

Extracts:
  - Revenue & employees (from text patterns)
  - Security controls (Firewall, MFA, EDR, etc.)
  - Policies (cyber, privacy, business continuity)
  - Policy dates, premium amounts (if available)
  - Industry/sector info

Uses pypdf for text extraction + regex for field matching.
Output: CSV with extracted fields per PDF for delta computation.
"""

import re
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple
from pypdf import PdfReader
import pandas as pd

logger = logging.getLogger(__name__)

# ============================================================================
# FIELD EXTRACTION PATTERNS (Regex)
# ============================================================================

REVENUE_PATTERNS = [
    r"(?:annual\s+)?revenue\s*(?:of|:|~)?\s*\$?\s*([\d,]+(?:\.\d{1,2})?)\s*(?:k|m|b|million|billion)?",
    r"(?:gross\s+)?sales\s*(?:of|:|~)?\s*\$?\s*([\d,]+(?:\.\d{1,2})?)\s*(?:k|m|b|million|billion)?",
    r"turnover\s*(?:of|:|~)?\s*\$?\s*([\d,]+(?:\.\d{1,2})?)\s*(?:k|m|b|million|billion)?",
    r"\$\s*([\d,]+(?:\.\d{1,2})?)\s*(?:k|m|b|million)?(?:\s+(?:in|of)\s+(?:revenue|sales))?",
]

EMPLOYEE_PATTERNS = [
    r"(?:number\s+of\s+)?employees?\s*(?::|~)?\s*(?:approximately|approx|around)?\s*(\d+(?:,\d{3})*)",
    r"(\d+(?:,\d{3})*)\s+(?:full-?time\s+)?employees?",
    r"headcount\s*(?::|~)?\s*(\d+(?:,\d{3})*)",
    r"fte\s*(?::|~)?\s*(\d+(?:,\d{3})*)",
]

CONTROL_KEYWORDS = {
    "Firewall": [r"\bfirewall\b", r"\bstateful\s+firewall\b"],
    "MFA": [r"\bmfa\b", r"\bmulti.?factor\s+auth", r"\b2fa\b"],
    "EDR": [r"\bedr\b", r"\bendpoint\s+detection", r"\bendpoint\s+response"],
    "IDS/IPS": [r"\bids\b", r"\bips\b", r"\bintrusion\s+(?:detection|prevention)"],
    "DLP": [r"\bdlp\b", r"\bdata\s+loss\s+prevention"],
    "SIEM": [r"\bsiem\b", r"\bsecurity\s+information"],
    "Encryption": [r"\bencryption\b", r"\bencrypted\b"],
    "Backup": [r"\bbackup", r"\bbackups\b"],
    "Incident Response": [r"\bincident\s+response", r"\bir\s+plan", r"\bincident\s+management"],
    "Security Awareness": [r"\bsecurity\s+awareness", r"\buser\s+training", r"\bsecurity\s+training"],
    "Patch Management": [r"\bpatch\s+management", r"\bpatching\b"],
    "Vulnerability": [r"\bvulnerability\s+(?:scanning|assessment)", r"\bvapt\b"],
}

POLICY_KEYWORDS = {
    "Cyber Insurance": [r"\bcyber\s+insurance\b", r"\bcyber\s+liability\b", r"\bcyberinsurance\b"],
    "Privacy Policy": [r"\bprivacy\s+polic(?:y|ies)\b", r"\bgdpr\b", r"\bccpa\b"],
    "Business Continuity": [r"\bbusiness\s+continuity", r"\bbc\s+plan", r"\bdisaster\s+recovery", r"\bdr\s+plan"],
    "Incident Response Plan": [r"\bincident\s+response\s+plan", r"\bresp\s+plan\b"],
    "Risk Management": [r"\brisk\s+management\b", r"\brisk\s+assessment\b"],
}

POLICY_DATE_PATTERN = r"(?:policy\s+)?(?:effective\s+)?(?:date|from)?\s*(?::|on\s+)?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})"
POLICY_EXPIRY_PATTERN = r"(?:expir(?:es?|ation)|until|through)\s*(?::|on\s+)?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})"
PREMIUM_PATTERN = r"(?:premium|cost|price)\s*(?::|of)?\s*\$\s*([\d,]+(?:\.\d{2})?)"

# ============================================================================
# PDF TEXT EXTRACTION
# ============================================================================

def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract all text from a PDF file path."""
    try:
        reader = PdfReader(str(pdf_path))
        text_parts = []
        for page in reader.pages:
            try:
                text_parts.append(page.extract_text())
            except Exception as e:
                logger.warning(f"Failed to extract text from page in {pdf_path.name}: {e}")
        return "\n".join(text_parts).lower()
    except Exception as e:
        logger.error(f"Failed to read PDF {pdf_path}: {e}")
        return ""


def extract_text_from_bytes(pdf_bytes: bytes) -> str:
    """Extract all text from PDF bytes (for Streamlit file uploader)."""
    import io
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text_parts = []
        for page in reader.pages:
            try:
                text_parts.append(page.extract_text() or "")
            except Exception:
                pass
        return "\n".join(text_parts).lower()
    except Exception as e:
        logger.error(f"Failed to read PDF bytes: {e}")
        return ""


def extract_product(text: str, known_products: list = None) -> str:
    """Extract product name from PDF text."""
    # If we have a known list, find the LONGEST exact product name in the text
    if known_products:
        text_lower = text.lower()
        best_match = None
        best_len = 0
        for prod in known_products:
            prod_lower = prod.lower()
            if prod_lower in text_lower and len(prod) > best_len:
                best_match = prod
                best_len = len(prod)
        if best_match:
            return best_match

    # Fallback: regex near coverage section
    for pattern in [
        r"product\s+requested\s*[:\-]\s*([^\n]{5,80})",
        r"coverage\s+requested[^\n]*\n[^\n]*product[^\n]*[:\-]\s*([^\n]{5,80})",
        r"product\s*[:\-]\s*([^\n]{5,80})",
    ]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip().title()
            if known_products:
                candidate_lower = candidate.lower()
                for prod in known_products:
                    prod_words = [w for w in prod.lower().split() if len(w) > 4]
                    if any(w in candidate_lower for w in prod_words):
                        return prod
            return candidate
    return None


def extract_broker(text: str, known_brokers: list = None) -> str:
    """Extract broker name from PDF text."""
    match = re.search(
        r"broker\s*(?:name|firm|agent)?\s*[:\-]\s*([^\n]{5,80})",
        text, re.IGNORECASE
    )
    if match:
        candidate = match.group(1).strip()
        # Remove any trailing reference numbers (e.g. "-- ref. AJG-TX-2026-4471")
        candidate = re.sub(r"\s*[-–]+\s*ref\..*$", "", candidate, flags=re.IGNORECASE).strip()
        if known_brokers:
            candidate_upper = candidate.upper()
            for broker in known_brokers:
                # Check if any significant word matches
                broker_words = [w for w in broker.upper().split() if len(w) > 3]
                if any(w in candidate_upper for w in broker_words):
                    return broker
        return candidate
    return None


def parse_pdf_from_upload(
    pdf_bytes: bytes,
    filename: str,
    known_products: list = None,
    known_brokers: list = None,
) -> Dict:
    """
    Parse a PDF from Streamlit file uploader bytes.
    Returns extracted fields dict ready for digital twin analysis.
    Pass known_products and known_brokers to improve matching.
    """
    text = extract_text_from_bytes(pdf_bytes)
    if not text.strip():
        return {"extraction_success": False, "filename": filename, "error": "No text extracted"}

    controls = extract_controls(text)
    policies = extract_policies(text)
    effective_date, expiry_date = extract_policy_dates(text)

    result = {
        "filename": filename,
        "extraction_success": True,
        "revenue_millions": extract_revenue(text),
        "employee_count": extract_employees(text),
        "policy_effective_date": effective_date,
        "policy_expiry_date": expiry_date,
        "premium_usd": extract_premium(text),
        "product": extract_product(text, known_products),
        "broker": extract_broker(text, known_brokers),
        "controls": controls,
        "policies": policies,
        # Flat control flags for digital twin
        "control_firewall": controls.get("Firewall", False),
        "control_mfa": controls.get("MFA", False),
        "control_edr": controls.get("EDR", False),
        "control_ids_ips": controls.get("IDS/IPS", False),
        "control_dlp": controls.get("DLP", False),
        "control_siem": controls.get("SIEM", False),
        "control_encryption": controls.get("Encryption", False),
        "control_backup": controls.get("Backup", False),
        "control_incident_response": controls.get("Incident Response", False),
        "control_security_awareness": controls.get("Security Awareness", False),
        "control_patch_management": controls.get("Patch Management", False),
        "control_vulnerability": controls.get("Vulnerability", False),
    }
    return result


# ============================================================================
# FIELD EXTRACTION FUNCTIONS
# ============================================================================

def extract_revenue(text: str) -> Optional[float]:
    """Extract revenue in millions from text."""
    for pattern in REVENUE_PATTERNS:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            try:
                amount_str = match.group(1).replace(",", "").replace(" ", "")
                amount = float(amount_str)
                
                # Detect multiplier (k/m/b)
                full_match = match.group(0).lower()
                if "billion" in full_match or "b" in full_match:
                    amount *= 1000
                elif "million" in full_match or "m" in full_match:
                    pass  # Already in millions
                elif "k" in full_match or "thousand" in full_match:
                    amount /= 1000
                
                # Return first valid match
                if amount > 0 and amount < 100000:  # Sanity check: <$100B
                    return amount
            except ValueError:
                continue
    
    return None


def extract_employees(text: str) -> Optional[int]:
    """Extract employee count from text."""
    for pattern in EMPLOYEE_PATTERNS:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            try:
                num_str = match.group(1).replace(",", "").strip()
                num = int(num_str)
                if num > 0 and num < 1000000:  # Sanity check: <1M employees
                    return num
            except ValueError:
                continue
    
    return None


NEGATION_PATTERNS = [
    r"\[no\]\s*{kw}",
    r"no\s+{kw}",
    r"not\s+(?:currently\s+)?(?:deployed|implemented|in\s+place|available)\s*[^\n]*{kw}",
    r"{kw}[^\n]{{0,60}}not\s+(?:currently|deployed|implemented|in\s+place)",
    r"{kw}[^\n]{{0,60}}does\s+not\s+(?:have|use|deploy)",
]


def _is_negated(text: str, keyword_pattern: str) -> bool:
    """Check if a control keyword is explicitly negated nearby."""
    # Extract a simplified keyword for negation check
    kw_simple = keyword_pattern.strip(r"\b").split(r"\b")[0].replace("\\", "").strip()
    for neg_tmpl in NEGATION_PATTERNS:
        neg_pat = neg_tmpl.format(kw=re.escape(kw_simple))
        if re.search(neg_pat, text, re.IGNORECASE):
            return True
    return False


def extract_controls(text: str) -> Dict[str, bool]:
    """
    Extract security controls presence (boolean flags).
    Priority:
      1. Explicit [YES]/[NO] markers (Zurich submission format)
      2. Negation context detection
      3. Keyword presence fallback
    """
    controls = {}

    for control_name, patterns in CONTROL_KEYWORDS.items():
        found = False
        explicit_set = False

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue

            start = max(0, match.start() - 120)
            end = min(len(text), match.end() + 120)
            context = text[start:end]

            # Priority 1: explicit [YES] / [NO] marker within 60 chars before keyword
            pre_context = text[max(0, match.start() - 60): match.start()]
            if re.search(r"\[yes\]", pre_context, re.IGNORECASE):
                found = True
                explicit_set = True
                break
            if re.search(r"\[no\]", pre_context, re.IGNORECASE):
                found = False
                explicit_set = True
                break

            # Priority 2: negation in context
            if _is_negated(context, pattern):
                found = False
                explicit_set = True
                break

            # Priority 3: keyword found without negation
            found = True
            break

        controls[control_name] = found

    return controls


def extract_policies(text: str) -> Dict[str, bool]:
    """
    Extract policy presence (boolean flags).
    
    Returns:
        Dict mapping policy name -> presence (True/False)
    """
    policies = {}
    
    for policy_name, patterns in POLICY_KEYWORDS.items():
        found = False
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                found = True
                break
        policies[policy_name] = found
    
    return policies


def extract_policy_dates(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract policy effective date and expiry date.
    
    Returns:
        Tuple of (effective_date, expiry_date) as strings (YYYY-MM-DD format)
    """
    effective_date = None
    expiry_date = None
    
    # Look for effective date
    match = re.search(POLICY_DATE_PATTERN, text, re.IGNORECASE)
    if match:
        effective_date = _normalize_date(match.group(1))
    
    # Look for expiry date
    match = re.search(POLICY_EXPIRY_PATTERN, text, re.IGNORECASE)
    if match:
        expiry_date = _normalize_date(match.group(1))
    
    return effective_date, expiry_date


def extract_premium(text: str) -> Optional[float]:
    """Extract policy premium in dollars."""
    match = re.search(PREMIUM_PATTERN, text, re.IGNORECASE)
    if match:
        try:
            amount_str = match.group(1).replace(",", "").strip()
            amount = float(amount_str)
            if amount > 0:
                return amount
        except ValueError:
            pass
    
    return None


def _normalize_date(date_str: str) -> str:
    """
    Convert date string to YYYY-MM-DD format.
    Handles MM/DD/YYYY, DD/MM/YYYY, etc.
    """
    # Try common formats
    for fmt in ["%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%d/%m/%y", 
                "%m-%d-%Y", "%m-%d-%y", "%d-%m-%Y", "%d-%m-%y"]:
        try:
            from datetime import datetime
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    
    # Return original if parsing fails
    return date_str.strip()


# ============================================================================
# MAIN EXTRACTION ORCHESTRATION
# ============================================================================

def parse_pdf_submission(pdf_path: Path, company_name: str) -> Dict:
    """
    Parse a single PDF submission and extract all fields.
    
    Args:
        pdf_path: Path to PDF file
        company_name: Name of company (for reference)
    
    Returns:
        Dict with extracted fields
    """
    logger.info(f"Parsing {pdf_path.name} for {company_name}")
    
    text = extract_text_from_pdf(pdf_path)
    if not text:
        logger.warning(f"No text extracted from {pdf_path.name}")
        return {
            "company_name": company_name,
            "pdf_file": pdf_path.name,
            "pdf_path": str(pdf_path),
            "extraction_success": False,
        }
    
    # Extract all fields
    controls = extract_controls(text)
    policies = extract_policies(text)
    effective_date, expiry_date = extract_policy_dates(text)
    
    result = {
        "company_name": company_name,
        "pdf_file": pdf_path.name,
        "pdf_path": str(pdf_path),
        "extraction_success": True,
        "revenue_millions": extract_revenue(text),
        "employee_count": extract_employees(text),
        "policy_effective_date": effective_date,
        "policy_expiry_date": expiry_date,
        "premium_usd": extract_premium(text),
    }
    
    # Add control flags
    for control_name, present in controls.items():
        result[f"control_{control_name.lower().replace(' ', '_').replace('/', '_')}"] = present
    
    # Add policy flags
    for policy_name, present in policies.items():
        result[f"policy_{policy_name.lower().replace(' ', '_')}"] = present
    
    return result


def parse_company_folder(company_folder: Path) -> list:
    """
    Parse all PDFs in a company folder.
    
    Args:
        company_folder: Path to company folder containing PDFs
    
    Returns:
        List of dicts (one per PDF) with extracted fields
    """
    results = []
    company_name = company_folder.name
    
    # Find all PDFs in folder (recursively)
    pdf_files = list(company_folder.glob("**/*.pdf"))
    logger.info(f"Found {len(pdf_files)} PDFs in {company_name}")
    
    for pdf_path in pdf_files:
        result = parse_pdf_submission(pdf_path, company_name)
        results.append(result)
    
    return results


def parse_all_companies(root_data_path: Path) -> pd.DataFrame:
    """
    Parse all company folders and return as DataFrame.
    
    Args:
        root_data_path: Path to root data folder containing company subfolders
    
    Returns:
        DataFrame with extracted fields (one row per PDF)
    """
    all_results = []
    
    # Find all company folders (Company 1, Company 2, etc.)
    company_folders = sorted([d for d in root_data_path.iterdir() if d.is_dir()])
    logger.info(f"Found {len(company_folders)} company folders")
    
    for company_folder in company_folders:
        results = parse_company_folder(company_folder)
        all_results.extend(results)
    
    df = pd.DataFrame(all_results)
    logger.info(f"Parsed {len(df)} total PDFs across all companies")
    
    return df


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    # Adjust path to your data folder
    data_root = Path(r"C:\Users\A.SANCHEZLORENTE\Zurich Insurance\Hyper Challenge 2026 - 04 - Leveraging historical data for new customers\Use Case Data")
    
    if data_root.exists():
        df = parse_all_companies(data_root)
        
        # Save results
        output_path = Path("data/parsed/pdf_extracted_fields.csv")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        logger.info(f"Saved {len(df)} results to {output_path}")
        
        print(f"\n✅ Extracted fields from {len(df)} PDFs")
        print(f"Columns: {list(df.columns)}")
        print(f"\nFirst extraction sample:")
        print(df.iloc[0] if len(df) > 0 else "No results")
    else:
        print(f"Data folder not found: {data_root}")
