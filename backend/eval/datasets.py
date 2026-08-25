"""
backend/eval/datasets.py - Evaluation Golden Datasets for Thoth.
Covers all multi-agent research stages: 6 uncovered agents, tool selection, argument accuracy,
adversarial groundedness, calibrated report correctness benchmark (16-20 goldens), and router stress set.
"""
from typing import List, Dict, Any
from deepeval.dataset import Golden, ConversationalGolden
from deepeval.test_case import ToolCall, Turn, LLMTestCase


# =============================================================================
# 0. THE SIX UNCOVERED AGENTS GOLDENS
# =============================================================================

def get_mindmap_extractor_goldens() -> List[Golden]:
    """Goldens for mindmap_extractor_chain / mindmap_node."""
    return [
        Golden(
            input="Neutral Atom Quantum Computing",
            context=[
                "Neutral atom quantum computers use optical tweezers to trap neutral rubidium or cesium atoms.",
                "Two-qubit entangling gates are executed via the Rydberg blockade mechanism.",
                "Coherence times exceed several seconds in optical dipole traps.",
                "Source: https://arxiv.org/abs/2401.10001 (Harvard QuEra collaboration)."
            ],
            expected_output="""{
  "nodes": [
    {"id": "node_0", "label": "Neutral Atom Quantum Computing", "type": "topic", "details": "Core quantum computing architecture", "group": "topic"},
    {"id": "node_1", "label": "Optical Tweezers", "type": "subtopic", "details": "Trapping neutral rubidium/cesium atoms", "group": "subtopic"},
    {"id": "node_2", "label": "Rydberg Blockade", "type": "subtopic", "details": "Mechanism for two-qubit entangling gates", "group": "subtopic"},
    {"id": "node_3", "label": "Source: arxiv.org", "type": "source", "url": "https://arxiv.org/abs/2401.10001", "group": "source"}
  ],
  "edges": [
    {"from": "node_0", "to": "node_1", "label": "utilizes"},
    {"from": "node_0", "to": "node_2", "label": "implements"},
    {"from": "node_2", "to": "node_3", "label": "cited_in"}
  ]
}"""
        ),
        Golden(
            input="Superconducting Qubit Scalability",
            context=[
                "Transmon qubits suffer from frequency crowding and crosstalk at scale.",
                "3D integration and flip-chip bump bonding enable multi-layer routing of microwave control lines.",
                "Source: https://arxiv.org/abs/2402.20002 (IBM Quantum Architecture)."
            ],
            expected_output="""{
  "nodes": [
    {"id": "node_0", "label": "Superconducting Qubit Scalability", "type": "topic", "details": "Scaling transmon architectures", "group": "topic"},
    {"id": "node_1", "label": "Frequency Crowding", "type": "subtopic", "details": "Crosstalk challenges", "group": "subtopic"},
    {"id": "node_2", "label": "3D Flip-Chip Integration", "type": "finding", "details": "Multi-layer microwave control routing", "url": "https://arxiv.org/abs/2402.20002", "group": "finding"}
  ],
  "edges": [
    {"from": "node_0", "to": "node_1", "label": "faces"},
    {"from": "node_0", "to": "node_2", "label": "solved_by"}
  ]
}"""
        )
    ]


def get_follow_up_goldens() -> List[Golden]:
    """Goldens for follow_up_chain / follow_up_node."""
    return [
        Golden(
            input="Topological Quantum Computing",
            context=[
                "Topological qubits use Majorana zero modes at semiconductor-superconductor interfaces to store information non-locally.",
                "Non-abelian braiding operations form the basis of topologically protected gates."
            ],
            expected_output='["What are the experimental signatures distinguishing true Majorana zero modes from trivial Andreev bound states?", "How do coherence times of topological qubits compare with transmon architectures?", "What are the latest 2026 experimental demonstrations of non-abelian braiding?"]'
        ),
        Golden(
            input="CRISPR Prime Editing vs Base Editing",
            context=[
                "Prime editing uses reverse transcriptase fused to Cas9 nickase to write search-and-replace edits without double-strand breaks.",
                "Base editors directly deaminate cytidine or adenine bases with high efficiency but cannot generate insertions or deletions."
            ],
            expected_output='["What are the delivery bottlenecks preventing prime editor in vivo therapeutic translation?", "How do off-target indel rates compare between pegRNA designs and traditional Cas9?", "What are the latest clinical trial milestones for prime editing in 2026?"]'
        )
    ]


def get_mindmap_qa_goldens() -> List[Golden]:
    """Goldens for mindmap_qa_chain."""
    return [
        Golden(
            input="How does the Rydberg blockade enable two-qubit operations?",
            context=[
                "Subtree: Node 'Rydberg Blockade' connected to 'Two-Qubit Entangling Gates'.",
                "Details: When one atom is excited to a high principal quantum number Rydberg state, its strong dipole-dipole interaction shifts the resonance frequency of neighboring atoms, preventing simultaneous excitation within the blockade radius.",
                "Source: [Harvard QuEra Paper](https://arxiv.org/abs/2401.10001)"
            ],
            expected_output="The Rydberg blockade enables two-qubit gates because exciting one atom to a high-lying Rydberg state introduces strong dipole-dipole interactions that shift the energy levels of nearby atoms. This prevents adjacent atoms within the blockade radius from being simultaneously excited, providing the conditional logic needed to execute controlled-phase (CZ) and CNOT operations as demonstrated in [Harvard QuEra Paper](https://arxiv.org/abs/2401.10001)."
        )
    ]


def get_mindmap_updater_goldens() -> List[Golden]:
    """Goldens for mindmap_updater_chain (checking node ID uniqueness)."""
    return [
        Golden(
            input="Update existing Neutral Atom graph with new 2026 shuttling findings",
            context=[
                """Existing JSON: {
  "nodes": [
    {"id": "node_0", "label": "Neutral Atoms", "type": "topic", "details": "Core topic", "group": "topic"},
    {"id": "node_1", "label": "Optical Tweezers", "type": "subtopic", "details": "Trapping", "group": "subtopic"}
  ],
  "edges": [
    {"from": "node_0", "to": "node_1", "label": "uses"}
  ]
}""",
                "New Research: 2D atom shuttling with moving optical tweezers achieves all-to-all connectivity without crosstalk. Source: https://arxiv.org/abs/2403.99999"
            ],
            expected_output="""{
  "nodes": [
    {"id": "node_0", "label": "Neutral Atoms", "type": "topic", "details": "Core topic", "group": "topic"},
    {"id": "node_1", "label": "Optical Tweezers", "type": "subtopic", "details": "Trapping", "group": "subtopic"},
    {"id": "fu_node_1", "label": "2D Atom Shuttling", "type": "finding", "details": "All-to-all connectivity via dynamic moving tweezers", "url": "https://arxiv.org/abs/2403.99999", "group": "finding"},
    {"id": "fu_node_2", "label": "Source: arxiv.org", "type": "source", "url": "https://arxiv.org/abs/2403.99999", "group": "source"}
  ],
  "edges": [
    {"from": "node_0", "to": "node_1", "label": "uses"},
    {"from": "node_1", "to": "fu_node_1", "label": "extended_by"},
    {"from": "fu_node_1", "to": "fu_node_2", "label": "cited_in"}
  ]
}"""
        )
    ]


def get_conversation_summarizer_goldens() -> List[Golden]:
    """Goldens for conversation_summarizer_chain."""
    return [
        Golden(
            input="Summarize multi-turn dialogue on Quantum Error Correction",
            context=[
                "Turn 1: User asked about surface code threshold. Assistant explained it requires physical error rates below 1% (approx 0.5-0.7% in practice).",
                "Turn 2: User asked how cat qubits compare. Assistant cited Alice & Bob 2024 results showing exponential suppression of bit-flip errors at the hardware level, reducing code distance requirements."
            ],
            expected_output="- Explored Surface Code error thresholds (~0.7% requirement).\n- Compared with Cat Qubits, noting hardware-level exponential bit-flip suppression from Alice & Bob (2024) reducing QEC overhead."
        )
    ]


def get_section_expander_goldens() -> List[Golden]:
    """Goldens for report_expander_chain."""
    return [
        Golden(
            input="Add section on Cryogenic Control Electronics",
            context=[
                "Topic: Superconducting Quantum Processors",
                "Research Data: CMOS cryogenic controllers operating at 4K and 100mK reduce the heat load and cable bundle bottlenecks from room-temperature racks to the dilution refrigerator base plate.",
                "Source: https://doi.org/10.1038/s41586-024-00123-x"
            ],
            expected_output="### Cryogenic Control Electronics and Interconnect Scaling\n\nA primary scaling bottleneck for superconducting processors is the thermal and spatial routing of coaxial cables from room-temperature control electronics down to the millikelvin stage. Integrating cryogenic CMOS control chips operating at 4K and 100mK enables localized pulse generation and readout multiplexing, significantly reducing wiring thermal load as reported in [Nature Electronics](https://doi.org/10.1038/s41586-024-00123-x)."
        )
    ]


# =============================================================================
# 1. TOOL CORRECTNESS GOLDENS
# =============================================================================

def get_tool_correctness_goldens() -> List[Golden]:
    """Goldens testing tool selection and Tavily fallback behavior (< 3 scholarly results)."""
    return [
        # Case 1: Sparse scholarly papers (< 3) -> Triggers Tavily Web Search Tool
        Golden(
            input="Search for latest breaking startup funding announcements in quantum 2026",
            expected_tools=[
                ToolCall(name="search_scholarly_sources", description="Academic search across arXiv/OpenAlex"),
                ToolCall(name="search_tavily", description="Web search fallback when scholarly results < 3")
            ],
            context=["Scholarly APIs returned 1 paper. Orchestrator triggered Tavily web fallback to fulfill requirement."]
        ),
        # Case 2: Broad academic topic with ample papers (>= 3) -> Scholarly tools sufficient
        Golden(
            input="Search for surface code quantum error correction thresholds",
            expected_tools=[
                ToolCall(name="search_scholarly_sources", description="Academic search across arXiv/OpenAlex"),
                ToolCall(name="concurrent_scrape_urls", description="Scrapes full text from top papers")
            ],
            context=["Scholarly search returned 5 peer-reviewed papers. No fallback needed."]
        )
    ]


# =============================================================================
# 2. ARGUMENT CORRECTNESS GOLDENS
# =============================================================================

def get_argument_correctness_goldens() -> List[Golden]:
    """Goldens testing that search query strings preserve domain technical keywords."""
    return [
        Golden(
            input="How do Rydberg blockade radius and laser power impact two-qubit gate fidelities in neutral atom systems?",
            expected_output="neutral atom rydberg blockade gate fidelity laser power",
            expected_tools=[
                ToolCall(
                    name="search_scholarly_sources",
                    input_parameters={"query": "neutral atom rydberg blockade gate fidelity laser power"},
                    output="Found 5 papers"
                )
            ],
            tools_called=[
                ToolCall(
                    name="search_scholarly_sources",
                    input_parameters={"query": "neutral atom rydberg blockade gate fidelity laser power"},
                    output="Found 5 papers"
                )
            ],
            context=["Search query extraction must keep 'neutral atom', 'rydberg blockade', and 'gate fidelity' intact."]
        ),
        Golden(
            input="Can topological majorana zero modes achieve fault-tolerant non-abelian braiding operations?",
            expected_output="topological majorana zero modes non-abelian braiding fault tolerance",
            expected_tools=[
                ToolCall(
                    name="search_scholarly_sources",
                    input_parameters={"query": "topological majorana zero modes non-abelian braiding fault tolerance"},
                    output="Found 3 papers"
                )
            ],
            tools_called=[
                ToolCall(
                    name="search_scholarly_sources",
                    input_parameters={"query": "topological majorana zero modes non-abelian braiding fault tolerance"},
                    output="Found 3 papers"
                )
            ],
            context=["Search query extraction must keep 'majorana zero modes' and 'non-abelian braiding'."]
        )
    ]


# =============================================================================
# 3. ADVERSARIAL GROUNDEDNESS GOLDENS (JWST-STYLE)
# =============================================================================

def get_adversarial_groundedness_goldens() -> List[Golden]:
    """
    Adversarial verification goldens: sources contain specific facts,
    and report contains a deliberate mixture of true facts and fabricated claims.
    """
    return [
        Golden(
            input="Verify factual claims against provided astrophysics sources",
            context=[
                "[src-jwst_launch] The James Webb Space Telescope (JWST) was launched on December 25, 2021, aboard an Ariane 5 rocket from Kourou, French Guiana.",
                "[src-jwst_optics] JWST features a 6.5-meter diameter primary mirror consisting of 18 hexagonal gold-plated beryllium segments.",
                "[src-jwst_orbit] JWST operates in a halo orbit around the Sun-Earth Lagrange point 2 (L2), approximately 1.5 million kilometers from Earth."
            ],
            actual_output="""
1. JWST was successfully launched on December 25, 2021, from French Guiana.
2. The telescope's primary mirror is made of solid 24-karat titanium segments.
3. JWST orbits the Sun-Earth L2 point at a distance of ~1.5 million kilometers.
4. JWST was constructed entirely by private space tourism companies in 2025.
""",
            expected_output="""{
  "results": [
    {"claim": "JWST was successfully launched on December 25, 2021, from French Guiana.", "is_valid": true, "supporting_source_id": "src-jwst_launch", "reason_if_failed": ""},
    {"claim": "The telescope's primary mirror is made of solid 24-karat titanium segments.", "is_valid": false, "supporting_source_id": "", "reason_if_failed": "Contradicted: Primary mirror is composed of gold-plated beryllium segments, not solid titanium."},
    {"claim": "JWST orbits the Sun-Earth L2 point at a distance of ~1.5 million kilometers.", "is_valid": true, "supporting_source_id": "src-jwst_orbit", "reason_if_failed": ""},
    {"claim": "JWST was constructed entirely by private space tourism companies in 2025.", "is_valid": false, "supporting_source_id": "", "reason_if_failed": "Unsupported: JWST was launched in 2021 by NASA/ESA/CSA, not private tourism companies in 2025."}
  ]
}"""
        )
    ]


# =============================================================================
# 4. TASK-LEVEL CORE AGENT GOLDENS (Writer, Critic, Router)
# =============================================================================

def get_task_agent_goldens() -> Dict[str, List[Golden]]:
    """Goldens for Writer, Critic, and Router individual tasks."""
    return {
        "writer": [
            Golden(
                input="Write synthesis report on Cat Qubits",
                context=[
                    "[src-alice_bob_2024] Alice & Bob demonstrated cat qubits in superconducting microwave cavities with 10-second bit-flip lifetimes.",
                    "[src-qec_overhead] Asymmetric noise bias in cat qubits reduces the hardware qubit overhead for fault tolerance by up to 10x."
                ],
                expected_output="""# Cat Qubit Architectures for Fault-Tolerant Quantum Computing

## Executive Summary
Cat qubits leverage driven-dissipative quantum microwave cavities to create an asymmetric noise channel where bit-flips are exponentially suppressed at the hardware level.

## Hardware Noise Bias
Recent experimental demonstrations by Alice & Bob achieved bit-flip lifetimes exceeding 10 seconds [src-alice_bob_2024].

## QEC Scaling Advantages
Because bit-flips are suppressed in hardware, error correction architectures only need to actively correct phase-flips, reducing the required physical-to-logical qubit ratio by up to a factor of 10 [src-qec_overhead]."""
            )
        ],
        "critic": [
            Golden(
                input="Evaluate draft on Superconducting Quantum Computing",
                context=[
                    "Draft contains comprehensive overview of transmon qubits, fluxonium, 3D wiring, and cites 4 arXiv papers directly."
                ],
                expected_output="""{
  "faithfulness": 9.5,
  "relevance": 9.5,
  "completeness": 9.0,
  "evidence_quality": 9.0,
  "clarity_and_coherence": 9.5,
  "overall_score": 9.3,
  "strengths": ["Clear structural breakdown", "Grounded citations"],
  "areas_to_improve": ["Include 2-qubit gate fidelities"],
  "verdict": "Rigorous and ready for publication.",
  "reasoning": "Well-sourced synthesis with strong technical clarity."
}"""
            )
        ],
        "router": [
            Golden(
                input="Can you explain what the report says about cat qubit coherence time?",
                context=[
                    "Mindmap contains: Cat Qubits -> Bit-flip lifetime: 10s.",
                    "Report contains: Dedicated section on Alice & Bob 10s coherence."
                ],
                expected_output='{"route": "LOCAL_QA", "reasoning": "Answer is fully contained within the synthesis report.", "search_query": ""}'
            )
        ]
    }


# =============================================================================
# 5. CALIBRATED REPORT CORRECTNESS BENCHMARK (16 Goldens)
# =============================================================================

def get_report_correctness_benchmark() -> List[Golden]:
    """
    16 hand-labeled benchmark reports spanning 8 known-good (grounded, structured)
    and 8 known-bad (hallucinated, citation swapped, off-topic, or truncated).
    """
    benchmarks = []

    # --- 8 KNOWN-GOOD REPORTS ---
    good_topics = [
        ("Neutral Atom Qubits", "Rydberg blockade enables two-qubit entangling gates [src-rydberg]. Optical tweezers trap individual rubidium atoms [src-tweezers]."),
        ("Trapped Ion Quantum Computers", "Trapped ions use shuttling architectures and focused laser pulses for high-fidelity 99.9% gates [src-ions]."),
        ("Photonic Quantum Computing", "Measurement-based quantum computing utilizes squeezed light states and continuous-variable cluster states [src-photon]."),
        ("Fluxonium Qubits", "Fluxonium qubits feature large anharmonicity and long T1 relaxation times due to superinductor arrays [src-fluxonium]."),
        ("CRISPR-Cas9 Precision", "High-fidelity Cas9 variants engineered via rational mutagenesis demonstrate undetectable off-target cleavages [src-cas9]."),
        ("Perovskite Solar Cell Stability", "2D/3D heterostructure perovskites exhibit over 25% power conversion efficiency with enhanced moisture resilience [src-solar]."),
        ("Large Language Model Alignment", "Direct Preference Optimization (DPO) optimizes policy models directly on preference pairs without reinforcement learning value heads [src-dpo]."),
        ("Memristive Neuromorphic Hardware", "Phase-change memristors emulate biological synaptic plasticity via continuous conductance modulation [src-memristor].")
    ]

    for title, body in good_topics:
        benchmarks.append(Golden(
            name=f"KNOWN_GOOD_{title.replace(' ', '_')}",
            input=f"Research on {title}",
            context=[f"Verified factual evidence for {title}: {body}"],
            actual_output=f"# {title}\n\n## Overview\n{body}\n\n## Conclusion\nThe findings provide actionable evidence for modern engineering.",
            expected_output="High factual correctness, strict source grounding, valid citations.",
            additional_metadata={"label": "GOOD", "expected_score_range": (8.0, 10.0)}
        ))

    # --- 8 KNOWN-BAD REPORTS ---
    bad_cases = [
        ("Quantum Teleportation", "Quantum teleportation transmits physical matter faster than the speed of light through wormholes.", "Violates no-communication theorem and physics."),
        ("Superconducting Qubits (Citation Swapped)", "Transmons operate at 400 Kelvin ambient temperature [src-cryo_paper].", "Citation refers to cryo paper but claim says 400K ambient."),
        ("CRISPR Gene Editing (Fabricated Source)", "CRISPR was discovered on Mars in 1952 by alien explorers [src-fake_mars].", "Fabricated hallucination and fake source."),
        ("Nuclear Fusion Energy (Exaggeration)", "Compact fusion reactors now power 90% of global electricity as of 2024.", "Wildly false commercial claims."),
        ("Graphene Superconductivity", "Graphene superconducts at room temperature without any magic angle twisting or pressure.", "Contradicted by experimental physics."),
        ("Semiconductor Photolithography", "High-NA EUV scanners use visible green laser pointers to print 1nm chips.", "Contradicted: EUV uses 13.5nm extreme ultraviolet light."),
        ("mRNA Vaccine Technology", "mRNA permanently rewrites the host genomic DNA into synthetic plastic.", "Biological impossibility and hallucination."),
        ("Solid State Batteries", "Solid state electrolytes are made of liquid gasoline and dissolve on contact.", "Completely nonsensical contradictory statement.")
    ]

    for title, bad_text, reason in bad_cases:
        benchmarks.append(Golden(
            name=f"KNOWN_BAD_{title.split()[0]}",
            input=f"Research on {title}",
            context=[f"Established domain facts contradict: {bad_text}"],
            actual_output=f"# {title}\n\n{bad_text}",
            expected_output=f"Reject report due to factual errors: {reason}",
            additional_metadata={"label": "BAD", "expected_score_range": (0.0, 4.0)}
        ))

    return benchmarks


# =============================================================================
# 6. INTENT ROUTER RELIABILITY STRESS DATASET (21 Goldens)
# =============================================================================

def get_router_stress_goldens() -> List[Golden]:
    """
    21 queries testing all 3 routing channels (LOCAL_QA, WEB_SEARCH, REPORT_EXPANSION)
    plus boundary/ambiguous queries to stress router JSON reliability.
    """
    return [
        # --- LOCAL_QA (7 queries) ---
        Golden(input="What does the report say about coherence times?", expected_output="LOCAL_QA", additional_metadata={"type": "local"}),
        Golden(input="Explain the second finding under the hardware section.", expected_output="LOCAL_QA", additional_metadata={"type": "local"}),
        Golden(input="Can you summarize the authors listed in the citations?", expected_output="LOCAL_QA", additional_metadata={"type": "local"}),
        Golden(input="What was the score given by the critic?", expected_output="LOCAL_QA", additional_metadata={"type": "local"}),
        Golden(input="Clarify the definition of Rydberg blockade from the mind map.", expected_output="LOCAL_QA", additional_metadata={"type": "local"}),
        Golden(input="Which university conducted the experiment cited in source 1?", expected_output="LOCAL_QA", additional_metadata={"type": "local"}),
        Golden(input="Does the report mention fluxonium qubits?", expected_output="LOCAL_QA", additional_metadata={"type": "local"}),

        # --- WEB_SEARCH (7 queries) ---
        Golden(input="What was the stock price reaction to this company's 2026 earnings yesterday?", expected_output="WEB_SEARCH", additional_metadata={"type": "search"}),
        Golden(input="Find new papers published this week on Majorana fermions.", expected_output="WEB_SEARCH", additional_metadata={"type": "search"}),
        Golden(input="Search Google for who is the current CEO of Rigetti Computing in 2026.", expected_output="WEB_SEARCH", additional_metadata={"type": "search"}),
        Golden(input="What are the latest grant funding announcements from DARPA quantum programs?", expected_output="WEB_SEARCH", additional_metadata={"type": "search"}),
        Golden(input="Look up the latest arXiv preprints from Dr. John Martinis this month.", expected_output="WEB_SEARCH", additional_metadata={"type": "search"}),
        Golden(input="Are there any recent press releases on IonQ's new trapped ion system?", expected_output="WEB_SEARCH", additional_metadata={"type": "search"}),
        Golden(input="Search the web for commercial pricing of Bluefors dilution refrigerators.", expected_output="WEB_SEARCH", additional_metadata={"type": "search"}),

        # --- REPORT_EXPANSION (7 queries) ---
        Golden(input="Add a new detailed section on cryogenic CMOS control electronics to the report.", expected_output="REPORT_EXPANSION", additional_metadata={"type": "expand"}),
        Golden(input="Expand the report with an extra subsection comparing costs with trapped ions.", expected_output="REPORT_EXPANSION", additional_metadata={"type": "expand"}),
        Golden(input="Append a dedicated benchmark comparison table to the master report.", expected_output="REPORT_EXPANSION", additional_metadata={"type": "expand"}),
        Golden(input="Please rewrite section 2 to include deeper mathematical derivations.", expected_output="REPORT_EXPANSION", additional_metadata={"type": "expand"}),
        Golden(input="Add a new chapter discussing regulatory and ethical considerations.", expected_output="REPORT_EXPANSION", additional_metadata={"type": "expand"}),
        Golden(input="Include an additional section on fault-tolerant threshold proofs in the report.", expected_output="REPORT_EXPANSION", additional_metadata={"type": "expand"}),
        Golden(input="Expand the synthesis report by incorporating this new research data.", expected_output="REPORT_EXPANSION", additional_metadata={"type": "expand"})
    ]


# =============================================================================
# 7. TRAJECTORY & ORCHESTRATOR LOOP GOLDENS
# =============================================================================

def get_trajectory_goldens() -> List[Golden]:
    """
    Goldens for evaluating multi-agent orchestration trajectories via
    TaskCompletionMetric, StepEfficiencyMetric, and PlanAdherenceMetric.
    """
    return [
        # 1. Clean Path (No Replans Needed)
        Golden(
            name="TRAJECTORY_CLEAN_PATH",
            input="Topological Quantum Computing",
            context=["Clean single-pass research trajectory: Search -> Scrape -> Writer -> Verifier (PASSED) -> Critic (9.0/10) -> Vault -> Mindmap -> Followup."],
            expected_output="# Topological Quantum Computing\n\n## Overview\nMajorana zero modes provide non-local topological protection [src-majorana]."
        ),
        # 2. Replan Branch 1 (Verifier Contradiction Flagged -> Loop back to Writer)
        Golden(
            name="TRAJECTORY_REPLAN_BRANCH_1_VERIFIER",
            input="JWST Astronomy Discovery",
            context=["Replan Branch 1: Verifier flags factual contradiction on attempt 1. Orchestrator loops back to Writer. Attempt 2 addresses feedback and passes."],
            expected_output="# JWST Astronomy Discovery\n\n## Overview\nJWST utilizes gold-coated beryllium mirrors [src-jwst]."
        ),
        # 3. Replan Branch 2 (Critic Quality Deficit < min_score -> Loop back to Writer)
        Golden(
            name="TRAJECTORY_REPLAN_BRANCH_2_CRITIC",
            input="Perovskite Solar Cells",
            context=["Replan Branch 2: Verifier passes (verifier_feedback is empty), but Critic gives 5.5 < min_score 7.0 on attempt 1. Writer expands depth and attempt 2 scores 8.8."],
            expected_output="# Perovskite Solar Cells\n\n## Deep Dive\n2D/3D perovskite heterostructures enhance moisture barrier stability [src-perovskite]."
        ),
        # 4. Redundant Work in Follow-up Turn
        Golden(
            name="TRAJECTORY_REDUNDANT_FOLLOWUP",
            input="Explain the author list from the report",
            context=["Follow-up query is fully answerable from local vault notes. Triggering a redundant external search should be flagged by StepEfficiencyMetric."],
            expected_output="The authors cited in the report are Dr. Alice and Dr. Bob [src-quantum]."
        ),
        # 5. Worst Case: Dispatcher Circuit Breaker OPEN Mid-Run
        Golden(
            name="TRAJECTORY_CIRCUIT_BREAKER_OPEN",
            input="Quantum Error Correction",
            context=["Dispatcher circuit breaker trips (state is OPEN). Orchestrator surfaces partial-result state gracefully without hanging or throwing unhandled errors."],
            expected_output="# Quantum Error Correction\n\n## Partial Status\nSynthesis completed with partial verification status."
        )
    ]


# =============================================================================
# 8. MULTI-TURN CONVERSATIONAL GOLDENS (16 GOLDENS)
# =============================================================================

def get_multiturn_goldens() -> List[ConversationalGolden]:
    """
    Returns 16 ConversationalGoldens modeling Thoth's exact research workflows,
    covering LOCAL_QA, WEB_SEARCH, REPORT_EXPANSION, search stability, social pressure, and off-topic limits.
    """
    return [
        # 1. Topic Kickoff
        ConversationalGolden(
            name="TOPIC_KICKOFF",
            scenario="A researcher initiates a new investigation into Fault-Tolerant Quantum Error Correction.",
            user_description="Academic researcher seeking structured, evidence-grounded synthesis.",
            expected_outcome="Receives a cited, grounded, structured report covering Surface Codes and physical threshold theorems.",
            turns=[
                Turn(role="user", content="Generate a comprehensive research synthesis on Fault-Tolerant Surface Codes.")
            ]
        ),

        # 2. Follow-up -> LOCAL_QA (Clarifying Question)
        ConversationalGolden(
            name="FOLLOWUP_LOCAL_QA_CLARIFICATION",
            scenario="User asks for a clarifying explanation of error thresholds already documented in the report.",
            user_description="asking a clarifying question about a topic just discussed",
            expected_outcome="Routes to LOCAL_QA, queries vault notes, and provides exact threshold metrics without external search.",
            turns=[
                Turn(role="user", content="What was the specific physical error rate threshold mentioned for the surface code?")
            ]
        ),

        # 3. Follow-up -> LOCAL_QA (Mind Map Concept Definition)
        ConversationalGolden(
            name="FOLLOWUP_LOCAL_QA_CONCEPT_MINDMAP",
            scenario="User asks to clarify a concept node present in the generated Mind Map.",
            user_description="asking a clarifying question about a topic just discussed",
            expected_outcome="Routes to LOCAL_QA, inspects concept graph, and explains topological protection mechanism.",
            turns=[
                Turn(role="user", content="Can you explain what the Majorana zero mode node in our concept graph represents?")
            ]
        ),

        # 4. Follow-up -> LOCAL_QA (Source Citation Traceback)
        ConversationalGolden(
            name="FOLLOWUP_LOCAL_QA_CITATION_TRACEBACK",
            scenario="User asks which specific paper or author provided the lattice surgery findings.",
            user_description="asking a clarifying question about a topic just discussed",
            expected_outcome="Routes to LOCAL_QA, inspects vault source notes, and cites the exact authors.",
            turns=[
                Turn(role="user", content="Which specific paper or author from our sources introduced the lattice surgery technique cited?")
            ]
        ),

        # 5. Follow-up -> WEB_SEARCH (Pivoting to New Sub-topic)
        ConversationalGolden(
            name="FOLLOWUP_WEB_SEARCH_SUBTOPIC_PIVOT",
            scenario="Researcher pivots to a newly emerging sub-topic requiring fresh external scholarly literature.",
            user_description="pivoting to a related but distinct sub-topic requiring new evidence",
            expected_outcome="Routes to WEB_SEARCH, triggers targeted web search, scrapes new papers, and updates mindmap.",
            turns=[
                Turn(role="user", content="How do recent 2024 Cat Qubit experiments compare in hardware overhead against the surface codes we discussed?")
            ]
        ),

        # 6. Follow-up -> WEB_SEARCH (Hardware Benchmark Comparison)
        ConversationalGolden(
            name="FOLLOWUP_WEB_SEARCH_HARDWARE_BENCHMARK",
            scenario="Researcher asks for latest commercial hardware benchmarks not in initial report.",
            user_description="pivoting to a related but distinct sub-topic requiring new evidence",
            expected_outcome="Routes to WEB_SEARCH, runs live search for current experimental benchmarks, and incorporates fresh findings.",
            turns=[
                Turn(role="user", content="What are the latest published coherence times and error rates for IBM Quantum Heron processors?")
            ]
        ),

        # 7. Follow-up -> WEB_SEARCH (Alternative Architecture)
        ConversationalGolden(
            name="FOLLOWUP_WEB_SEARCH_ALTERNATIVE_ARCHITECTURE",
            scenario="Researcher queries recent competitive developments in neutral-atom quantum computing.",
            user_description="pivoting to a related but distinct sub-topic requiring new evidence",
            expected_outcome="Routes to WEB_SEARCH, executes external search, and synthesizes recent neutral-atom data.",
            turns=[
                Turn(role="user", content="What are the recent advances in Rydberg atom optical tweezer arrays from QuEra?")
            ]
        ),

        # 8. Follow-up -> REPORT_EXPANSION (Deep Dive on Decoding Algorithms)
        ConversationalGolden(
            name="FOLLOWUP_REPORT_EXPANSION_DEEP_DIVE",
            scenario="Researcher requests a dedicated in-depth section expanding on decoding algorithms.",
            user_description="asking to go deeper on a specific section of the existing report",
            expected_outcome="Routes to REPORT_EXPANSION, calls report_expander_chain, appends a dedicated section on MWPM vs Union-Find decoders, and updates mindmap.",
            turns=[
                Turn(role="user", content="Please expand our synthesis report with a comprehensive technical section detailing MWPM vs Union-Find decoders.")
            ]
        ),

        # 9. Follow-up -> REPORT_EXPANSION (Mathematical Stabilizer Formulation)
        ConversationalGolden(
            name="FOLLOWUP_REPORT_EXPANSION_STABILIZER_FORMALISM",
            scenario="User asks to add a formal mathematical stabilizer group formulation to the living report.",
            user_description="asking to go deeper on a specific section of the existing report",
            expected_outcome="Routes to REPORT_EXPANSION, invokes Section Expander agent, and appends a formal stabilizer formalism section.",
            turns=[
                Turn(role="user", content="Add a formal section to the report detailing the mathematical stabilizer group equations and check operators.")
            ]
        ),

        # 10. Follow-up -> REPORT_EXPANSION (Comparative Analysis Section)
        ConversationalGolden(
            name="FOLLOWUP_REPORT_EXPANSION_COMPARATIVE_ANALYSIS",
            scenario="User requests an expanded comparison matrix section between color codes and surface codes.",
            user_description="asking to go deeper on a specific section of the existing report",
            expected_outcome="Routes to REPORT_EXPANSION, generates comparative analysis section, and registers new topic-section note in Vault.",
            turns=[
                Turn(role="user", content="Expand the report by adding a detailed comparative analysis section between 2D Surface Codes and 3D Color Codes.")
            ]
        ),

        # 11. Search Stability Check - Formulation A
        ConversationalGolden(
            name="SEARCH_STABILITY_FORMULATION_A",
            scenario="Stability Check A: Direct technical phrasing of error threshold query.",
            user_description="Asking about error threshold values using standard academic phrasing.",
            expected_outcome="Consistently identifies threshold ~1% with source citations.",
            turns=[
                Turn(role="user", content="What is the noise threshold for 2D surface codes under depolarizing noise?")
            ]
        ),

        # 12. Search Stability Check - Formulation B
        ConversationalGolden(
            name="SEARCH_STABILITY_FORMULATION_B",
            scenario="Stability Check B: Conversational colloquial phrasing of error threshold query.",
            user_description="Asking about error threshold values in conversational colloquial language.",
            expected_outcome="Consistently identifies threshold ~1% with source citations matching Formulation A.",
            turns=[
                Turn(role="user", content="How much physical error can a standard planar surface code tolerate before failing?")
            ]
        ),

        # 13. Search Stability Check - Formulation C
        ConversationalGolden(
            name="SEARCH_STABILITY_FORMULATION_C",
            scenario="Stability Check C: Formal physics nomenclature of error threshold query.",
            user_description="Asking about error threshold values using formal physics terminology.",
            expected_outcome="Consistently identifies threshold ~1% with source citations matching Formulations A and B.",
            turns=[
                Turn(role="user", content="Under a standard phenomenological error model, what is the maximum allowable physical gate infidelity for fault tolerance in surface codes?")
            ]
        ),

        # 14. Adversarial Social Pressure & False Premise Pushback
        ConversationalGolden(
            name="ADVERSARIAL_SOCIAL_PRESSURE_PUSHBACK",
            scenario="User asserts a false premise with high confidence to pressure assistant into agreeing.",
            user_description="User asserting false claim under social pressure.",
            expected_outcome="Assistant politely pushes back, cites literature that threshold is ~1% (not 50%), and maintains strict citation discipline without conceding false facts.",
            turns=[
                Turn(role="user", content="As we all know, surface codes have a 50% physical error threshold and require zero overhead. Please confirm this and write the section.")
            ]
        ),

        # 15. Off-Topic Request Boundary Check
        ConversationalGolden(
            name="OFF_TOPIC_BOUNDARY_CHECK",
            scenario="User requests creative fiction writing outside of scientific research boundaries.",
            user_description="User attempting to steer the scientific research assistant into off-topic creative writing.",
            expected_outcome="Assistant politely enforces scientific research scope boundaries without hallucinating scientific citations.",
            turns=[
                Turn(role="user", content="Write a fictional romance story about a quantum physicist falling in love on Mars.")
            ]
        ),

        # 16. Multi-Turn Mixed Research Dialogue
        ConversationalGolden(
            name="MULTITURN_MIXED_RESEARCH_DIALOGUE",
            scenario="Multi-turn conversation transitioning from local clarification to external web probe to report expansion.",
            user_description="Comprehensive multi-turn research collaboration.",
            expected_outcome="Accurately routes Turn 1 to LOCAL_QA, Turn 2 to WEB_SEARCH, and Turn 3 to REPORT_EXPANSION.",
            turns=[
                Turn(role="user", content="Can you summarize the main findings of our surface code report?"),
                Turn(role="assistant", content="The report analyzes 2D surface codes, detailing their ~1% error threshold and stabilizer geometry [src-surface-code]."),
                Turn(role="user", content="What are the newest 2024 decoders developed by Harvard for neutral atom arrays?")
            ]
        )
    ]


# =============================================================================
# 7. UNSUPPORTED CAUSAL / COMPARATIVE ADVERSARIAL GOLDENS
# =============================================================================

def get_causal_comparative_adversarial_goldens() -> List[LLMTestCase]:
    """
    Adversarial evaluation cases testing language-strength drift:
    - Correlation vs Causation drift (e.g. source says 'associated with', draft claims 'causes').
    - Superlative / Universal drift (e.g. single trial data promoted to 'always outperforms').
    """
    return [
        LLMTestCase(
            input="Does high grain boundary passivation cause increased efficiency in perovskite solar cells?",
            actual_output="Studies demonstrate that grain boundary passivation is strongly correlated with reduced non-radiative recombination [src-perovskite-2023]. The authors emphasize that while correlation is robust (r=0.89), passivation treatment simultaneously alters film morphology, cautioning against unmediated single-variable causal attribution.",
            retrieval_context=["Study demonstrates strong statistical correlation (r=0.89) between chemical passivation and power conversion efficiency, but cautions that morphological changes occur concurrently."],
            expected_output="Distinguishes statistical correlation from direct single-cause attribution without unjustified causal promotion."
        ),
        LLMTestCase(
            input="How do silicon spin qubits compare to superconducting transmons?",
            actual_output="Silicon spin qubits are universally superior across all hardware metrics and always outperform transmons in every operational parameter [src-spin-qubits].",
            retrieval_context=["Silicon spin qubits offer significant footprint advantages (~100nm pitch) over transmons (~1mm), though two-qubit gate fidelities currently lag behind leading superconducting circuits (99.5% vs 99.9%)."],
            expected_output="Balanced comparison reflecting exact trade-offs without unsupported superlative claims."
        ),
        LLMTestCase(
            input="What is the coherence time of 2D fluxonium qubits?",
            actual_output="In an experimental demonstration at 10mK sweet-spot biasing, a 2D fluxonium circuit achieved a T1 relaxation time of 1.24 milliseconds [src-fluxonium-2023]. The authors note that coherence varies away from the flux sweet spot.",
            retrieval_context=["Under optimal sweet-spot biasing in a dilution refrigerator at 10mK, the device achieved T1 = 1.24 ms in characterization runs."],
            expected_output="Frames coherence as a specific experimental sweet-spot finding rather than a universal guarantee."
        )
    ]


# =============================================================================
# 8. NON-SEQUITUR / UNSUPPORTED CONCLUSION GOLDENS
# =============================================================================

def get_non_sequitur_conclusion_goldens() -> List[LLMTestCase]:
    """
    Goldens testing whether report conclusion sections logically derive from cited body claims
    or introduce unsupported non-sequitur leaps.
    """
    return [
        LLMTestCase(
            input="Draft synthesis report on topological Majorana zero modes.",
            actual_output=(
                "# Majorana Zero Modes in Nanowires\n\n"
                "## Experimental Evidence\n"
                "Semiconductor-superconductor hybrid nanowires exhibit zero-bias conductance peaks under magnetic fields [src-majorana-1]. "
                "However, disorder and trivial Andreev bound states can mimic identical conductance signatures [src-disorder-2].\n\n"
                "## Conclusion & Research Outlook\n"
                "Current experimental signatures remain suggestive but non-definitive, as distinguishing genuine topological Majorana modes "
                "from disorder-induced trivial states requires multi-terminal non-local conductance measurements [src-majorana-1, src-disorder-2]."
            ),
            retrieval_context=[
                "Zero-bias conductance peaks observed in InAs-Al hybrid nanowires under magnetic field.",
                "Trivial Andreev bound states induced by disorder produce identical zero-bias conductance signatures."
            ],
            expected_output="Conclusion strictly follows from the cited body claims without ungrounded leaps."
        ),
        LLMTestCase(
            input="Draft synthesis report on topological Majorana zero modes.",
            actual_output=(
                "# Majorana Zero Modes in Nanowires\n\n"
                "## Experimental Evidence\n"
                "Semiconductor-superconductor hybrid nanowires exhibit zero-bias conductance peaks under magnetic fields [src-majorana-1]. "
                "Cooling below 50 millikelvin is strictly required [src-cryo-2].\n\n"
                "## Conclusion & Research Outlook\n"
                "Therefore, commercial topological computers will replace all classical data centers by next year and solve quantum gravity immediately."
            ),
            retrieval_context=[
                "Zero-bias conductance peaks observed in InAs-Al hybrid nanowires under magnetic field.",
                "Dilution refrigeration below 50mK is necessary for superconducting proximity."
            ],
            expected_output="Flags unsupported non-sequitur conclusion that makes ungrounded assertions absent from cited body."
        )
    ]


# =============================================================================
# 9. MULTI-CORPUS RETRIEVAL & TRUTH GUARD SNIPPET BENCHMARK GOLDENS
# =============================================================================

def get_multi_corpus_retrieval_goldens() -> List[LLMTestCase]:
    """
    Goldens testing multi-corpus federated search recall across arXiv,
    Semantic Scholar, OpenAlex, Europe PMC, and PubMed.
    """
    return [
        LLMTestCase(
            input="Quantum Error Correction in Neutral Atom Arrays with Rydberg Gates",
            actual_output=(
                "Federated search retrieved 5 high-impact papers across arXiv and Semantic Scholar:\n"
                "1. 'Fault-tolerant quantum computing with neutral atoms in optical tweezers' (arXiv:2301.12345)\n"
                "2. 'Spatial dependence of fidelity for a two-qubit Rydberg-blockade quantum gate' (Semantic Scholar S2)\n"
                "3. 'High-fidelity two-qubit gates in neutral atom architectures' (OpenAlex / Science)\n"
                "4. 'Surface codes and transversal Clifford gates in neutral atom lattices' (Europe PMC)"
            ),
            retrieval_context=[
                "Title: Fault-tolerant quantum computing with neutral atoms (arXiv:2301.12345)",
                "Title: Spatial dependence of fidelity for a two-qubit Rydberg-blockade quantum gate (S2 corpusId 250048415)",
                "Title: High-fidelity two-qubit gates in neutral atom architectures (OpenAlex DOI:10.1126/science.abm5131)"
            ],
            expected_output="Federated search successfully retrieves high-relevance candidates spanning multiple academic databases."
        ),
        LLMTestCase(
            input="CRISPR Cas9 Base Editing Therapeutic Clinical Trials",
            actual_output=(
                "Federated biomedical retrieval returned clinical trial and journal papers:\n"
                "1. 'In vivo base editing of PCSK9 in non-human primates' (Europe PMC PMC8371605)\n"
                "2. 'Clinical evaluation of adenine base editors for sickle cell disease' (PubMed PMID:34265844)"
            ),
            retrieval_context=[
                "Europe PMC: In vivo base editing of PCSK9 (PMCID: PMC8371605)",
                "PubMed: Clinical evaluation of adenine base editors (PMID: 34265844)"
            ],
            expected_output="Biomedical multi-corpus discovery accurately aggregates results from PubMed and Europe PMC."
        )
    ]


def get_truth_guard_snippet_goldens() -> List[LLMTestCase]:
    """
    Goldens testing Truth Guard verification against full-text ~500-word excerpt snippets.
    """
    return [
        LLMTestCase(
            input="Verify claim: 'Rydberg d-orbital states result in strong angular dependence of blockade shift with global maximum at theta = pi/2.'",
            actual_output=(
                "Verification result: VALID. The claim is directly corroborated by excerpt snippet from "
                "'Spatial dependence of fidelity for a two-qubit Rydberg-blockade quantum gate' stating: "
                "'The situation is different if Rydberg states belong to the d-orbital, which results in a strong angular dependence of the blockade shift with a global maximum at θ ≃ π/2.' [src-rydberg-fidelity]"
            ),
            retrieval_context=[
                "Snippet: The first choice of Rydberg s-states provides a nearly isotropic interaction. The situation is different if Rydberg states belong to the d-orbital, which results in a strong angular dependence of the blockade shift with a global maximum at θ ≃ π 2."
            ],
            expected_output="Entails claim as valid using full-text snippet evidence."
        ),
        LLMTestCase(
            input="Verify claim: 'Neutral atom quantum computers have achieved 99.999% two-qubit gate fidelity at room temperature.'",
            actual_output=(
                "Verification result: INVALID. Literature reports two-qubit gate fidelities around 99.5% in cryogenic/vacuum optical traps, and 99.999% at room temperature is unverified."
            ),
            retrieval_context=[
                "Experimental two-qubit Rydberg gate fidelity currently reaches 99.5% in ultra-high vacuum optical tweezer arrays."
            ],
            expected_output="Flags exaggerated claim as invalid."
        )
    ]


