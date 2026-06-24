"""
Data models for submissions, customers, and deltas.
Using Pydantic for type safety and validation.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class Control(BaseModel):
    """Security control or risk mitigation measure."""
    name: str
    category: str  # e.g., "authentication", "backup", "incident_response"
    maturity: Optional[int] = None  # 0-5 scale
    present: bool = True
    
    class Config:
        extra = "allow"

class Submission(BaseModel):
    """A single submission application."""
    submission_id: str
    customer_id: str
    submission_date: datetime
    effective_date: datetime
    product: str
    broker: str
    status: str  # "Received", "Quoted", "Declined", "Rated", "QNT"
    
    # Financial
    quoted_premium: Optional[float] = None
    revenue: Optional[float] = None
    employees: Optional[int] = None
    
    # Risk profile
    controls: List[Control] = Field(default_factory=list)
    risk_score: Optional[float] = None  # 0-100, higher = higher risk
    decision: Optional[str] = None  # What did we do?
    
    # Metadata
    underwriter: Optional[str] = None
    naics_code: Optional[str] = None
    sic_code: Optional[str] = None
    
    class Config:
        extra = "allow"

class Customer(BaseModel):
    """A customer with multiple submissions."""
    customer_id: str
    name: str  # Anonymized name or identifier
    submissions: List[Submission] = Field(default_factory=list)
    lob: str  # Line of business (e.g., "Cyber", "Financial Lines")
    primary_broker: Optional[str] = None
    
    class Config:
        extra = "allow"

class Delta(BaseModel):
    """Changes between two submissions for the same customer."""
    from_submission_id: str
    to_submission_id: str
    months_between: int
    
    # Numerical deltas
    revenue_delta_pct: Optional[float] = None  # % change
    employee_delta: Optional[int] = None  # absolute change
    premium_delta: Optional[float] = None
    
    # Categorical changes
    controls_added: List[str] = Field(default_factory=list)
    controls_removed: List[str] = Field(default_factory=list)
    controls_degraded: List[str] = Field(default_factory=list)  # Maturity decreased
    controls_improved: List[str] = Field(default_factory=list)  # Maturity increased
    
    # Decision changes
    decision_from: Optional[str] = None
    decision_to: Optional[str] = None
    
    # Composite risk flag
    risk_increased: bool = False
    anomaly_score: Optional[float] = None  # 0-100, higher = more anomalous
    
    class Config:
        extra = "allow"

class RiskScore(BaseModel):
    """Risk assessment for a submission."""
    submission_id: str
    customer_id: str
    score: float  # 0-100, higher = higher risk
    components: Dict[str, float] = Field(default_factory=dict)  # Breakdown: {"revenue_change": 20, "control_regression": 10, ...}
    confidence: float = 1.0  # 0-1
    recommendation: str  # "FAST_TRACK", "STANDARD_UW", "FRESH_UW"
    reasoning: List[str] = Field(default_factory=list)
    
    class Config:
        extra = "allow"

class KGNode(BaseModel):
    """A node in the knowledge graph."""
    node_id: str
    node_type: str  # "customer", "submission", "control", "broker", "cluster"
    attributes: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        extra = "allow"

class KGEdge(BaseModel):
    """An edge in the knowledge graph."""
    from_node_id: str
    to_node_id: str
    relationship_type: str  # "submitted", "has_control", "associated_with", etc.
    weight: float = 1.0  # Edge strength
    attributes: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        extra = "allow"
