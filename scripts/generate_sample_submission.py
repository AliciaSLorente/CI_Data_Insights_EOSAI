"""
Generate a realistic sample submission PDF for testing the New Submission Analyzer.
Based on a real STANDARD_UW profile: Software company, Security & Privacy product.
"""

from fpdf import FPDF
from pathlib import Path
from datetime import date

OUT_PATH = Path("data/sample_submission_MeridianTech.pdf")


class SubmissionPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.set_fill_color(0, 60, 120)
        self.set_text_color(255, 255, 255)
        self.cell(0, 12, "ZURICH INSURANCE -- SPECIALTIES SUBMISSION APPLICATION", fill=True, ln=True)
        self.set_text_color(0, 0, 0)
        self.set_font("Helvetica", "", 9)
        self.cell(0, 6, f"Security & Privacy | Cyber Liability | Date: {date.today().strftime('%d %B %Y')}", ln=True)
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Page {self.page_no()} -- CONFIDENTIAL -- Zurich Insurance Group", align="C")

    def section_title(self, title):
        self.set_font("Helvetica", "B", 11)
        self.set_fill_color(220, 235, 250)
        self.cell(0, 8, f"  {title}", fill=True, ln=True)
        self.ln(2)

    def field_row(self, label, value):
        self.set_font("Helvetica", "B", 9)
        self.cell(70, 6, label + ":", ln=False)
        self.set_font("Helvetica", "", 9)
        self.cell(0, 6, str(value), ln=True)

    def control_row(self, control, present, note=""):
        icon = "[YES]" if present else "[NO] "
        color = (0, 128, 0) if present else (180, 0, 0)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*color)
        self.cell(10, 5, icon, ln=False)
        self.set_text_color(0, 0, 0)
        self.cell(80, 5, control, ln=False)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(80, 80, 80)
        self.cell(0, 5, note, ln=True)
        self.set_text_color(0, 0, 0)


def generate():
    pdf = SubmissionPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # ── Section 1: Applicant Information ──────────────────────────────────────
    pdf.section_title("1. APPLICANT INFORMATION")
    pdf.field_row("Company Name", "Meridian Tech Solutions, Inc.")
    pdf.field_row("Primary Contact", "Sarah Mitchell, CFO")
    pdf.field_row("Address", "1420 Harbor Blvd, Suite 300, Houston, TX 77002")
    pdf.field_row("Website", "www.meridiantechsolutions.com")
    pdf.field_row("NAICS Code", "511210 -- Software Publishers")
    pdf.field_row("SIC Code", "7372 -- Prepackaged Software")
    pdf.field_row("Years in Operation", "12 years (Founded 2013)")
    pdf.ln(4)

    # ── Section 2: Financial Profile ──────────────────────────────────────────
    pdf.section_title("2. FINANCIAL PROFILE")
    pdf.field_row("Annual Revenue", "$45.2 million (FY2025)")
    pdf.field_row("Revenue Growth (YoY)", "+18% vs FY2024 ($38.4M)")
    pdf.field_row("Number of Employees", "280 full-time employees")
    pdf.field_row("Contractors / Third Parties", "Approximately 45 contractors")
    pdf.field_row("Primary Markets", "Healthcare SaaS, Financial Services platforms")
    pdf.field_row("Data Records Held", "~1.2 million customer records (PII + PHI)")
    pdf.ln(4)

    # ── Section 3: Coverage Requested ─────────────────────────────────────────
    pdf.section_title("3. COVERAGE REQUESTED")
    pdf.field_row("Product", "Security & Privacy Broad Primary")
    pdf.field_row("Policy Effective Date", "01/07/2026")
    pdf.field_row("Policy Expiry Date", "01/07/2027")
    pdf.field_row("Limits Requested", "$5,000,000 per occurrence / $5,000,000 aggregate")
    pdf.field_row("Retention / Deductible", "$50,000")
    pdf.field_row("Estimated Premium", "$72,000")
    pdf.field_row("Broker", "Arthur J. Gallagher & Co. -- ref. AJG-TX-2026-4471")
    pdf.ln(4)

    # ── Section 4: Security Controls ──────────────────────────────────────────
    pdf.section_title("4. SECURITY CONTROLS & CYBER POSTURE")

    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 5, "Please confirm which controls are currently in place:", ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    controls = [
        ("Firewall (Next-Gen / Stateful)", True, "Palo Alto Networks NGFW -- all perimeter and internal segments"),
        ("Multi-Factor Authentication (MFA)", True, "Okta MFA enforced for all users including remote access"),
        ("Endpoint Detection & Response (EDR)", False, "CrowdStrike contract under evaluation -- target Q3 2026"),
        ("Intrusion Detection / Prevention (IDS/IPS)", False, "Not currently deployed -- on security roadmap"),
        ("Data Loss Prevention (DLP)", False, "Basic email DLP only -- no endpoint DLP"),
        ("SIEM / Security Monitoring", False, "Log aggregation via Splunk (limited ruleset)"),
        ("Data Encryption (at rest & in transit)", True, "AES-256 at rest, TLS 1.3 in transit -- all customer data"),
        ("Backup & Recovery Systems", True, "Daily encrypted backups to AWS S3 + Azure Blob -- tested quarterly"),
        ("Incident Response Plan", True, "IR plan documented and tested -- last tabletop exercise March 2026"),
        ("Security Awareness Training", True, "Annual training + monthly phishing simulations (KnowBe4)"),
        ("Patch Management Program", True, "Monthly patching cycle -- critical patches within 72 hours"),
        ("Vulnerability Scanning / Assessment", True, "Quarterly external scan (Tenable) + annual pen test"),
    ]

    for ctrl_name, present, note in controls:
        pdf.control_row(ctrl_name, present, note)

    pdf.ln(4)

    # ── Section 5: Policies & Compliance ──────────────────────────────────────
    pdf.section_title("5. POLICIES & COMPLIANCE")

    policies = [
        ("Cyber Insurance (prior coverage)", True, "Covered by AXA XL 2025 policy -- $3M limit, no claims"),
        ("Privacy Policy (published)", True, "GDPR and CCPA compliant -- last updated January 2026"),
        ("Business Continuity Plan (BCP)", False, "Partial BCP in place -- full plan under development"),
        ("Incident Response Plan (IRP)", True, "Formal IRP in place -- reviewed annually"),
        ("Risk Management Framework", True, "NIST CSF adopted -- annual risk assessment completed"),
    ]

    for pol_name, present, note in policies:
        pdf.control_row(pol_name, present, note)

    pdf.ln(4)

    # ── Section 6: Claims History ──────────────────────────────────────────────
    pdf.section_title("6. PRIOR CLAIMS HISTORY (Last 5 Years)")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5,
        "No cyber or security & privacy claims in the last 5 years.\n"
        "One minor data incident in 2023 (accidental email exposure, no PII affected, "
        "no regulatory action, self-reported to legal counsel only)."
    )
    pdf.ln(4)

    # ── Section 7: Additional Information ─────────────────────────────────────
    pdf.section_title("7. ADDITIONAL RISK INFORMATION")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5,
        "Meridian Tech Solutions provides B2B SaaS platforms for healthcare billing "
        "and financial services workflow automation. The company processes PHI under HIPAA "
        "Business Associate Agreements with 14 healthcare clients.\n\n"
        "Revenue growth of 18% YoY is driven by 3 new enterprise contracts signed in Q1 2026. "
        "Headcount expected to grow from 280 to 340 by end of 2026.\n\n"
        "The company is actively investing in security posture: EDR deployment planned for Q3 2026, "
        "SOC 2 Type II certification in progress (target: Q4 2026)."
    )
    pdf.ln(4)

    # ── Signature ─────────────────────────────────────────────────────────────
    pdf.section_title("8. DECLARATION")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5,
        "I declare that the information provided in this application is true and complete "
        "to the best of my knowledge. I understand that any material misrepresentation may "
        "void coverage."
    )
    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(80, 6, "Signed: Sarah Mitchell, CFO", ln=False)
    pdf.cell(0, 6, f"Date: {date.today().strftime('%d/%m/%Y')}", ln=True)

    # Save
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUT_PATH))
    print(f"Generated: {OUT_PATH}")
    print(f"Profile: SIC 7372 (Prepackaged Software), Revenue $45.2M, 280 employees")
    print(f"Controls: Firewall YES, MFA YES, EDR NO, Encryption YES, Backup YES, IR YES")
    print(f"Expected recommendation: STANDARD_UW (missing EDR, IDS/IPS, DLP, SIEM)")


if __name__ == "__main__":
    generate()
