#!/usr/bin/env python3
"""
Thoth Database Seeding Tool.

Seeds high-quality demo research sessions, comprehensive reports, and knowledge
vault notes into the target database (SQLite store.db or Supabase Postgres).

Usage:
    python scripts/db/seed.py [--target sqlite|supabase] [--reset]
"""

import os
import sys
import uuid
import datetime
import argparse
import json
import logging

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

from backend.core.config import get_settings
from backend.core.logging import get_logger

logger = get_logger("ThothSeed")

DEMO_SESSIONS = [
    {
        "id": "session-demo-001",
        "topic": "Fault-Tolerant Quantum Computing with Neutral Atom Arrays",
        "status": "completed",
        "state": {
            "topic": "Fault-Tolerant Quantum Computing with Neutral Atom Arrays",
            "chat_turns": [
                {
                    "turn": 1,
                    "user_query": "What are the primary error thresholds for Rydberg atom arrays?",
                    "assistant_response": "Neutral atom systems typically achieve two-qubit gate fidelities around 99.5%, with fault-tolerant thresholds for surface and color codes estimated at ~1%.",
                    "route": "LOCAL_QA"
                }
            ],
            "follow_up_questions": [
                "How do shuttling latencies compare with superconducting interconnects?",
                "What are the dominant optical loss mechanisms during two-qubit entanglement?"
            ]
        }
    },
    {
        "id": "session-demo-002",
        "topic": "State-Space Models vs Transformers for Long-Context Reasoning",
        "status": "completed",
        "state": {
            "topic": "State-Space Models vs Transformers for Long-Context Reasoning",
            "chat_turns": [
                {
                    "turn": 1,
                    "user_query": "Explain linear attention trade-offs in Mamba-2 versus full quadratic attention.",
                    "assistant_response": "Mamba-2 achieves sub-quadratic O(N) inference throughput via structured state-space matrices, but trades off recall accuracy in associative memory retrieval tasks.",
                    "route": "LOCAL_QA"
                }
            ],
            "follow_up_questions": [
                "Does hybrid SSM-Transformer attention resolve associative retrieval degradation?",
                "What are the hardware efficiency ceilings on H100 Tensor Cores?"
            ]
        }
    }
]

DEMO_REPORTS = [
    {
        "id": "report-demo-001",
        "session_id": "session-demo-001",
        "topic": "Fault-Tolerant Quantum Computing with Neutral Atom Arrays",
        "markdown": """# Fault-Tolerant Quantum Computing with Neutral Atom Arrays

## Executive Summary
Neutral-atom quantum architectures have emerged as leading candidates for scalable quantum computing, leveraging optical tweezer arrays to position hundreds of individual atoms with sub-micron precision.

## Key Breakthroughs
- **Two-Qubit Gate Fidelities**: Recent experimental benchmarks report gate fidelities exceeding 99.5% using Rydberg excitation protocols.
- **Dynamic Reconfigurability**: Optical shuttling allows non-local connectivity, dramatically reducing SWAP overheads in topological code lattices.

## Challenges
- Optical scattering and decoherence during shuttling operations.
- Scaling beyond $10^4$ physical qubits requires cryogenic optical cavities.
""",
        "sources": [
            {
                "title": "Quantum Computation with Neutral Atoms in Optical Tweezers",
                "url": "https://arxiv.org/abs/2301.00001",
                "domain": "arxiv.org",
                "citations": 142
            },
            {
                "title": "High-Fidelity Rydberg Quantum Gates",
                "url": "https://arxiv.org/abs/2302.00002",
                "domain": "arxiv.org",
                "citations": 88
            }
        ]
    },
    {
        "id": "report-demo-002",
        "session_id": "session-demo-002",
        "topic": "State-Space Models vs Transformers for Long-Context Reasoning",
        "markdown": """# State-Space Models vs Transformers for Long-Context Reasoning

## Abstract
This evaluation contrasts structured state-space models (Mamba, S4) with standard multi-head self-attention mechanisms in sequence lengths exceeding 128k tokens.

## Findings
1. **Computational Complexity**: SSMs scale with $O(N)$ memory and time complexity during recurrent token generation.
2. **Associative Retrieval Bottlenecks**: Pure SSM architectures struggle with multi-hop needle-in-a-haystack tasks compared to full attention matrices.
3. **Hybrid Architectures**: Interleaving 1 attention layer every 4 SSM blocks matches transformer expressivity while cutting FLOPs by 60%.
""",
        "sources": [
            {
                "title": "Mamba: Linear-Time Sequence Modeling with Selective State Spaces",
                "url": "https://arxiv.org/abs/2312.00752",
                "domain": "arxiv.org",
                "citations": 420
            }
        ]
    }
]

def seed_sqlite(db_path: str, reset: bool = False):
    from backend.memory.db import init_db, save_session, save_report
    init_db(db_path)
    logger.info(f"Seeding SQLite database at '{db_path}'...")

    for s in DEMO_SESSIONS:
        save_session(
            session_id=s["id"],
            topic=s["topic"],
            status=s["status"],
            state=s["state"],
            db_path=db_path
        )
        logger.info(f"  [+] Seeded Session: {s['id']} ({s['topic']})")

    for r in DEMO_REPORTS:
        save_report(
            session_id=r["session_id"],
            topic=r["topic"],
            report_text=r["markdown"],
            sources=r["sources"],
            db_path=db_path,
            report_id=r["id"]
        )
        logger.info(f"  [+] Seeded Report:  {r['id']} for session {r['session_id']}")

def seed_supabase(reset: bool = False):
    settings = get_settings()
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        logger.warning("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY missing. Falling back to SQLite.")
        seed_sqlite(settings.DB_PATH, reset=reset)
        return

    try:
        from supabase import create_client
        client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

        logger.info("Seeding Supabase Postgres database...")
        for s in DEMO_SESSIONS:
            client.table("sessions").upsert({
                "id": s["id"],
                "topic": s["topic"],
                "status": s["status"],
                "state": s["state"]
            }).execute()
            logger.info(f"  [+] Seeded Supabase Session: {s['id']}")

        for r in DEMO_REPORTS:
            client.table("reports").upsert({
                "id": r["id"],
                "session_id": r["session_id"],
                "topic": r["topic"],
                "markdown": r["markdown"],
                "sources": r["sources"]
            }).execute()
            logger.info(f"  [+] Seeded Supabase Report:  {r['id']}")

    except ImportError:
        logger.error("'supabase' Python library not installed. Falling back to SQLite seed.")
        seed_sqlite(settings.DB_PATH, reset=reset)

def main():
    parser = argparse.ArgumentParser(description="Seed demo sessions and reports into database")
    parser.add_argument("--target", choices=["sqlite", "supabase", "auto"], default="auto", help="Database target")
    parser.add_argument("--reset", action="store_true", help="Reset existing demo records")
    args = parser.parse_args()

    settings = get_settings()
    target = args.target
    if target == "auto":
        target = "supabase" if (settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY) else "sqlite"

    print("=" * 70)
    print(f"THOTH SEED TOOL - Target: {target.upper()}")
    print("=" * 70)

    if target == "supabase":
        seed_supabase(reset=args.reset)
    else:
        seed_sqlite(settings.DB_PATH, reset=args.reset)

    print("\nDatabase seeding completed successfully.")
    print("=" * 70)

if __name__ == "__main__":
    main()
