from datetime import datetime
import random
from flask import Blueprint, request, jsonify
from utils.rbac import role_required

career_bp = Blueprint('careers', __name__, url_prefix='/api/careers')

# Seeded active career openings at Inventra AI
CAREER_JOBS = [
    {
        "id": "job-ml-01",
        "title": "Lead Machine Learning Engineer (Demand & Time-Series)",
        "department": "AI & Data Science",
        "location": "Bengaluru / Hybrid / Remote",
        "type": "Full-Time",
        "experience": "4 - 8 Years",
        "salary_range": "₹32,00,000 - ₹48,00,000 + Equity",
        "tags": ["Python", "scikit-learn", "LightGBM", "Time-Series", "FastAPI"],
        "description": "Architect and advance Inventra's proprietary retail demand forecasting models. You will design adaptive ensembles (GBDT, Random Forest, ARIMA-hybrid) operating over billions of transaction records.",
        "responsibilities": [
            "Scale continuous automated model retraining pipelines across thousands of multi-echelon retail SKUs.",
            "Engineer low-latency inference services serving live reorder recommendations to enterprise clients.",
            "Collaborate with supply chain domain experts to integrate lead-time uncertainty and dynamic safety stock thresholds.",
            "Optimize local offline LLM and tabular inference runtimes."
        ],
        "requirements": [
            "Strong track record deploying production ML models in retail, logistics, or quantitative finance.",
            "Deep expertise with Python, PyTorch/scikit-learn, Pandas, and spatial-temporal feature engineering.",
            "Experience with distributed model serving and Dockerized cloud/on-prem environments.",
            "B.Tech / M.Tech in Computer Science, Data Science, or related quantitative field."
        ]
    },
    {
        "id": "job-fs-02",
        "title": "Senior Full-Stack Product Engineer (React + Python)",
        "department": "Core Platform Engineering",
        "location": "Remote / Bengaluru",
        "type": "Full-Time",
        "experience": "3 - 6 Years",
        "salary_range": "₹22,00,000 - ₹34,00,000 + Stock Options",
        "tags": ["React", "Vite", "Tailwind CSS", "Flask", "PostgreSQL", "Recharts"],
        "description": "Craft intuitive, blazing-fast interfaces and robust backend APIs for modern retail operators, warehouse floor staff, and executive supply chain officers.",
        "responsibilities": [
            "Develop high-performance data visualizations, real-time KPI streaming feeds, and visual purchase order orchestration tools.",
            "Implement enterprise Role-Based Access Control (RBAC), privacy data masking, and multi-tenant security layers.",
            "Design clean, versioned RESTful APIs with SQLAlchemy, PostgreSQL, and background task processing.",
            "Ensure sub-second page loads and fluid 60fps micro-interactions."
        ],
        "requirements": [
            "Strong command of modern React (Hooks, Context, Vite, Tailwind CSS) and state management.",
            "Solid experience with Python web frameworks (Flask, FastAPI, or Django) and relational databases.",
            "Eye for micro-interactions, responsive typography, and enterprise design aesthetics.",
            "Passion for building software that directly impacts physical goods fulfillment."
        ]
    },
    {
        "id": "job-sc-03",
        "title": "Supply Chain & Multi-Criteria Sourcing Specialist",
        "department": "Operations & Sourcing",
        "location": "Mumbai / Gurugram / Hybrid",
        "type": "Full-Time",
        "experience": "2 - 5 Years",
        "salary_range": "₹16,00,000 - ₹26,00,000",
        "tags": ["Procurement", "Supplier Matrix", "Vendor Management", "Safety Stock"],
        "description": "Guide our algorithmic multi-criteria supplier ranking matrix. You will bridge physical manufacturer relationships with algorithmic lead time and fill-rate evaluation.",
        "responsibilities": [
            "Benchmark vendor performance across unit economics, verified lead days, MOQ structures, and quality scores.",
            "Refine multi-objective scoring formulas for automated procurement triggers.",
            "Work directly with enterprise retail partners to audit physical warehouse restock workflows.",
            "Draft replenishment playbook templates for diverse verticals (electronics, FMCG, apparel)."
        ],
        "requirements": [
            "2+ years in procurement, supply chain consulting, or operations planning.",
            "Familiarity with inventory replenishment formulas (EOQ, safety stock buffer, lead-time variance).",
            "Strong communication and analytical problem-solving skills."
        ]
    },
    {
        "id": "job-ae-04",
        "title": "Enterprise Solutions Architect & Account Director",
        "department": "Client Growth & Solutions",
        "location": "Bengaluru / Delhi NCR / Remote",
        "type": "Full-Time",
        "experience": "5 - 10 Years",
        "salary_range": "₹28,00,000 - ₹45,00,000 + Performance Bonus",
        "tags": ["Enterprise SaaS", "Retail ERP Integration", "SAP / Oracle", "Pre-Sales"],
        "description": "Lead technical integrations with Tier-1 retail chains, FMCG conglomerates, and regional distributors migrating to autonomous replenishment.",
        "responsibilities": [
            "Map enterprise client legacy ERP databases into Inventra's telemetry and prediction pipelines.",
            "Deliver executive demonstrations showcasing margin lift, stock-out reduction, and automated PO generation.",
            "Act as trusted technical advisor from discovery to post-deployment scaling."
        ],
        "requirements": [
            "Demonstrated experience in B2B enterprise software or retail consulting.",
            "Understanding of retail POS/ERP systems (SAP, Oracle Retail, Microsoft Dynamics).",
            "Executive-grade presentation and stakeholder management capabilities."
        ]
    }
]

# In-memory storage for applications
APPLICATIONS = [
    {
        "id": "APP-2026-901",
        "job_id": "job-ml-01",
        "job_title": "Lead Machine Learning Engineer",
        "full_name": "Arjun Sharma",
        "email": "arjun.ml@example.com",
        "phone": "+91 98765 43210",
        "experience_years": "5.5",
        "portfolio_url": "https://github.com/arjun-ml",
        "cover_note": "Excited about retail demand forecasting using temporal transformer and GBDT architectures.",
        "status": "Reviewing",
        "applied_at": "2026-10-05T14:30:00"
    }
]

@career_bp.route('/jobs', methods=['GET'])
def get_jobs():
    """Return all active job openings."""
    return jsonify({
        'jobs': CAREER_JOBS,
        'total': len(CAREER_JOBS),
        'perks': [
            {"title": "Competitive Pay & Equity", "desc": "Top-tier compensation benchmarks with high-upside stock grants."},
            {"title": "Remote-First Flexibility", "desc": "Work wherever you do your best thinking with home office setup stipends."},
            {"title": "GPU & ML Compute Budget", "desc": "Dedicated cloud compute clusters for experiments and prototyping."},
            {"title": "Comprehensive Healthcare", "desc": "100% health coverage for you and your dependents with mental wellness support."},
            {"title": "Learning & Conferences", "desc": "₹1,50,000 annual budget for workshops, books, and international AI summits."}
        ]
    }), 200

@career_bp.route('/apply', methods=['POST'])
def submit_application():
    """Submit a new job application."""
    data = request.get_json() or {}
    
    full_name = data.get('full_name', '').strip()
    email = data.get('email', '').strip()
    job_id = data.get('job_id', '')
    
    if not full_name or not email or not job_id:
        return jsonify({'error': 'Name, email, and job position are required.'}), 400
        
    matching_job = next((j for j in CAREER_JOBS if j['id'] == job_id), None)
    job_title = matching_job['title'] if matching_job else data.get('job_title', 'General Application')

    app_id = f"APP-{datetime.utcnow().year}-{random.randint(1000, 9999)}"
    
    application = {
        "id": app_id,
        "job_id": job_id,
        "job_title": job_title,
        "full_name": full_name,
        "email": email,
        "phone": data.get('phone', ''),
        "experience_years": str(data.get('experience_years', '')),
        "portfolio_url": data.get('portfolio_url', ''),
        "cover_note": data.get('cover_note', ''),
        "status": "Submitted",
        "applied_at": datetime.utcnow().isoformat()
    }
    
    APPLICATIONS.append(application)
    
    return jsonify({
        'message': f"Application submitted successfully! Your application reference is {app_id}.",
        'application_id': app_id,
        'job_title': job_title,
        'applicant': full_name
    }), 201

@career_bp.route('/applications', methods=['GET'])
def get_applications():
    """List received candidate applications."""
    return jsonify({
        'applications': APPLICATIONS,
        'count': len(APPLICATIONS)
    }), 200
