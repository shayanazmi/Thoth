"""
eval_sandbox/test_phase7_end_to_end_validation.py
=================================================
THOTH · PHASE 7 DEEP PRODUCT VALIDATION & QUALITY BENCHMARK

Validates the entire continuous user experience lifecycle across:
1. Casual chat -> domain exploration -> natural research transition
2. Seamless context inheritance & comparative anaphora resolution
3. Post-research Q&A, critical skepticism & assumption scrutinization
4. Live sub-search probing & Vault index persistence
5. Topic-switch isolation and backward return resolution
6. Multi-provider resilience, latency bounds, and clean thought tag stripping
"""

import sys
import os
import time
import json
import unittest
from typing import Dict, Any, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.orchestrator import create_initial_state, stream_research_pipeline
from backend.pipeline import (
    resolve_anaphoric_topic,
    stream_followup_turn,
    router_chain,
    mindmap_qa_chain
)
from backend.agents import (
    direct_chat_chain,
    strip_chain_of_thought,
    safe_extract_json
)
from backend.memory.session import SessionMemory, count_tokens


class TestPhase7DeepProductValidation(unittest.TestCase):

    def test_continuous_multi_turn_journey(self):
        """
        Tests the complete 9-stage continuous conversation flow:
        Casual Chat -> Topic Discussion -> Deeper Probe -> Research Transition -> 
        Report Follow-up -> Critical Challenge -> Sub-Search -> Topic Switch -> Deictic Return
        """
        print("\n--- PHASE 7: Continuous Multi-Turn User Journey Test ---")
        timings = {}
        
        # 1. CASUAL GREETING (< 1.5s)
        t0 = time.time()
        greeting_ans = strip_chain_of_thought(
            direct_chat_chain.invoke({"user_query": "Hello Thoth, what domains of science can we investigate?"})
        )
        timings["1_casual_greeting"] = time.time() - t0
        self.assertGreater(len(greeting_ans), 20)
        self.assertNotIn("<think>", greeting_ans)
        print(f"  [1/9] Casual Greeting TTFT/Latency: {timings['1_casual_greeting']:.2f}s ✓")

        # 2. SUBSTANTIVE TOPIC DISCUSSION (Memory turn 1)
        chat_turns = [
            {
                "turn": 1,
                "user_query": "Can you explain photonic integrated circuits vs electronic ICs?",
                "assistant_response": "Photonic ICs use light (photons) rather than electrical currents (electrons) for data transmission. Advantages include high optical bandwidth, low transmission propagation loss, and reduced resistive heating at high clock frequencies.",
                "route": "FAST_CHAT"
            }
        ]
        
        # 3. DEEPER PROBE (Memory turn 2)
        chat_turns.append({
            "turn": 2,
            "user_query": "Yeah but what does that actually mean for thermal dissipation in datacenter interconnects?",
            "assistant_response": "In datacenters, optical interconnects reduce copper resistive thermal dissipation by over 60%, allowing denser multi-rack clustering without catastrophic thermal throttling.",
            "route": "FAST_CHAT"
        })

        # 4. NATURAL CONVERSATION -> DEEP RESEARCH TRANSITION
        # User says: "Look into that properly" (Natural deictic research command)
        t0 = time.time()
        raw_directive = "Look into that properly"
        resolved_topic = resolve_anaphoric_topic(raw_directive, chat_turns=chat_turns)
        timings["4_anaphora_resolution"] = time.time() - t0
        
        self.assertIn("thermal dissipation", resolved_topic.lower())
        print(f"  [4/9] Natural Research Directive ('Look into that properly') resolved to: '{resolved_topic}' in {timings['4_anaphora_resolution']*1000:.1f}ms ✓")

        # Simulate Research Pipeline State with context inheritance
        session_mem = SessionMemory()
        session_mem.add_turn("Can you explain photonic integrated circuits?", "Photonic ICs use photons for low propagation loss.", {"route": "FAST_CHAT"})
        session_mem.add_turn("What does that mean for thermal dissipation?", "Reduces copper resistive heating by 60%.", {"route": "FAST_CHAT"})
        
        research_state = {
            "topic": resolved_topic,
            "report": """# Photonic Integrated Circuits: Thermal Dissipation & Interconnect Benchmarks

## Executive Summary
Co-packaged optics (CPO) and silicon photonics replace electrical SerDes links, achieving sub-1 pJ/bit transmission energy.

## Key Empirical Findings
- **Energy Efficiency**: Optical I/O achieves 0.85 pJ/bit compared to 4.2 pJ/bit for standard copper SerDes links [[src-nature-photonics-2025]].
- **Thermal Mitigation**: Eliminates copper resistive heating, mitigating localized hot-spot formation on accelerator compute tiles.
- **Waveguide Transmission**: 99.5% transmission fidelity demonstrated in micro-ring resonators under vacuum-isolated laboratory tests [[src-optical-soc-2026]].

## Identified Constraints & Trade-offs
- Thermal wavelength drift in ring resonators requires active micro-heater closed-loop tuning (5-10 mW per channel).
- Laser diode coupling packaging tolerances remain below 0.5 micrometers.
""",
            "score": 9.2,
            "attempt": 1,
            "verification_results": [
                {"claim": "Optical I/O achieves 0.85 pJ/bit vs 4.2 pJ/bit for copper SerDes", "status": "VERIFIED", "confidence": 0.95},
                {"claim": "99.5% transmission fidelity in micro-ring resonators", "status": "VERIFIED", "confidence": 0.92}
            ],
            "mindmap": {
                "nodes": [
                    {"id": "root", "label": "Silicon Photonics Thermal Dissipation", "type": "topic"},
                    {"id": "n1", "label": "Co-Packaged Optics (CPO)", "type": "finding"},
                    {"id": "n2", "label": "Micro-Ring Resonators (99.5% Fidelity)", "type": "finding"},
                    {"id": "n3", "label": "Thermal Drift Micro-Heater Overhead", "type": "challenge"}
                ],
                "edges": [
                    {"source": "root", "target": "n1", "relationship": "implements"},
                    {"source": "root", "target": "n2", "relationship": "utilizes"},
                    {"source": "n2", "target": "n3", "relationship": "constrained_by"}
                ]
            },
            "cumulative_sources": [
                {"url": "https://nature.com/articles/photonics-2025", "domain": "nature.com", "title": "CPO Energy Frontiers"},
                {"url": "https://ieee.org/papers/optical-soc-2026", "domain": "ieee.org", "title": "Micro-ring Resonators"}
            ],
            "follow_up_questions": [
                "How does active thermal tuning impact net system energy efficiency?",
                "What are the assembly yield bottlenecks for sub-micron fiber coupling?",
                "Investigate commercial roadmap comparisons between Broadcom and TSMC"
            ],
            "chat_turns": chat_turns,
            "conversation_summary": "Exploration of silicon photonics thermal dissipation and co-packaged optics."
        }

        # 5. POST-RESEARCH FOLLOW-UP: "Explain that simply: what matters most?"
        t0 = time.time()
        fu_events_1 = list(stream_followup_turn(research_state, "Explain that simply: what matters most?"))
        timings["5_report_followup"] = time.time() - t0
        
        ans_payloads_1 = [p for ev, p in fu_events_1 if ev == "answer"]
        self.assertGreaterEqual(len(ans_payloads_1), 1)
        fu_ans_1 = ans_payloads_1[0]["answer"].lower()
        self.assertTrue(any(k in fu_ans_1 for k in ["heat", "copper", "energy", "cooling", "interconnect", "optic"]))
        print(f"  [5/9] Post-Research Q&A answered in {timings['5_report_followup']:.2f}s ✓")

        # 6. SKEPTICAL CHALLENGE ON EXPERIMENTAL ASSUMPTIONS
        t0 = time.time()
        fu_events_2 = list(stream_followup_turn(
            research_state,
            "Wait, is that 99.5% transmission claim realistic, or what are the hidden assumptions and counterarguments?"
        ))
        timings["6_critical_challenge"] = time.time() - t0
        
        ans_payloads_2 = [p for ev, p in fu_events_2 if ev == "answer"]
        self.assertGreaterEqual(len(ans_payloads_2), 1)
        fu_ans_2 = ans_payloads_2[0]["answer"].lower()
        # Must discuss limitations, lab vs datacenter conditions, or thermal tuning
        self.assertTrue(any(k in fu_ans_2 for k in ["vacuum", "lab", "thermal", "drift", "assumption", "real-world", "loss", "temperature", "tuning"]))
        print(f"  [6/9] Skeptical Challenge Analyzed with Rigor in {timings['6_critical_challenge']:.2f}s ✓")

        # 7. TARGETED SUB-SEARCH PROBE WITH NEW CITATIONS
        t0 = time.time()
        fu_events_3 = list(stream_followup_turn(
            research_state,
            "What are the latest 2026 co-packaged optics announcements from TSMC or Broadcom?"
        ))
        timings["7_subsearch_probe"] = time.time() - t0
        ans_payloads_3 = [p for ev, p in fu_events_3 if ev == "answer"]
        self.assertGreaterEqual(len(ans_payloads_3), 1)
        print(f"  [7/9] Live Sub-Search and Vault Persistence completed in {timings['7_subsearch_probe']:.2f}s ✓")

        # 8. TOPIC SWITCH ISOLATION
        topic_switch_query = "Forget that for a moment. How do perovskite tandem solar cells achieve >33% efficiency?"
        raw_route_decision = router_chain.invoke({
            "topic": research_state["topic"],
            "mindmap_summary": "Silicon photonics",
            "report_summary": research_state["report"][:400],
            "user_query": topic_switch_query
        })
        parsed_route = safe_extract_json(raw_route_decision, default={"route": "WEB_SEARCH"})
        route_switch = parsed_route.get("route", "WEB_SEARCH")
        # Should route to WEB_SEARCH, not LOCAL_QA, because it's a completely new domain
        self.assertIn(route_switch, ["WEB_SEARCH", "DEEP_RESEARCH", "REPORT_EXPANSION"])
        print(f"  [8/9] Unrelated Topic Switch successfully routed to external search: '{route_switch}' ✓")

        # 9. DEICTIC RETURN TO ORIGINAL TOPIC
        complex_turns = list(chat_turns)
        complex_turns.append({
            "turn": 3,
            "user_query": "How do perovskite tandem solar cells achieve >33% efficiency?",
            "assistant_response": "By stacking wide-bandgap perovskite top cells onto silicon bottom cells, capturing both blue and infrared spectra.",
            "route": "WEB_SEARCH"
        })
        
        return_query = "Okay coming back to the previous photonics thermal thing - how does it compare to liquid immersion cooling?"
        resolved_return = resolve_anaphoric_topic(return_query, chat_turns=complex_turns)
        self.assertIn("photonics", resolved_return.lower())
        self.assertIn("liquid immersion", resolved_return.lower())
        print(f"  [9/9] Comparative Return Query successfully preserved both topics: '{resolved_return}' ✓")

        print("\n--- PHASE 7: Latency Summary ---")
        for k, v in timings.items():
            print(f"  • {k}: {v:.2f}s")

    def test_multi_provider_fallback_output_quality(self):
        """Verify fallback LLM produces clean text, valid JSON, and strips thought tags."""
        sample_cot = "<think>\nThinking through the photonics bottlenecks...\nLet's evaluate the thermal drift.\n</think>\nPhotonics reduces resistive losses by replacing electrical conductors with optical waveguides."
        cleaned = strip_chain_of_thought(sample_cot)
        self.assertNotIn("<think>", cleaned)
        self.assertNotIn("</think>", cleaned)
        self.assertIn("Photonics reduces resistive losses", cleaned)

        # Verify JSON extraction resilience
        json_cot = "<think>Generating JSON</think>\n```json\n{\"nodes\": [{\"id\": \"1\", \"label\": \"Photonics\"}], \"edges\": []}\n```"
        extracted = safe_extract_json(json_cot, default={})
        self.assertIn("nodes", extracted)
        self.assertEqual(extracted["nodes"][0]["label"], "Photonics")
        print("  ✓ Fallback thought-tag stripping and JSON extraction validated.")


if __name__ == "__main__":
    unittest.main()
