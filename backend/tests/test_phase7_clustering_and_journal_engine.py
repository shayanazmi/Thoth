"""
THOTH Phase 7 Verification Test Suite
Verifies Deliverable A (Semantic Literature Clustering & Citation Network Graph)
and Deliverable B (Automated Journal Submission Formatting Engine).
"""

import io
import json
import os
import tempfile
import unittest
import zipfile

from fastapi.testclient import TestClient

from backend.api.routes_prisma import router as prisma_router
from backend.api.routes_workspace import router as workspace_router
from backend.main import app
from backend.intellectual_rigour.clustering import (
    CitationEdge,
    CitationNode,
    ClusteringResult,
    LiteratureCitationGraph,
    ThematicCluster,
    build_literature_corpus,
    compute_citation_network_metrics,
    compute_thematic_clusters,
    generate_citation_network_mermaid,
    normalize_paper_id,
    run_literature_clustering_and_graph,
)
from backend.memory.db import (
    add_snowball_candidate_db,
    get_citation_graph_db,
    get_connection,
    get_literature_clustering_db,
    init_db,
    save_brief_db,
    save_journal_submission_db,
    save_manuscript_db,
    save_manuscript_revision_db,
    save_prisma_review_db,
    save_project_db,
    save_screening_decision_db,
    save_snowball_run_db,
)
from backend.workspace.journal_formatter import (
    JournalPreset,
    PRESET_CATALOG,
    build_journal_submission_package,
    generate_acm_latex,
    generate_ieee_latex,
    generate_nature_latex,
    generate_neurips_latex,
    generate_submission_checklist,
    get_journal_submission_db,
    list_journal_submissions_db,
)


class TestPhase7ClusteringAndJournalEngine(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "test_phase7.db")
        init_db(self.db_path)
        self.client = TestClient(app)

    def tearDown(self):
        try:
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
            os.rmdir(self.tmp_dir)
        except Exception:
            pass

    # ==========================================================================
    # Deliverable A: Clustering & Citation Network Tests
    # ==========================================================================

    def test_normalize_paper_id(self):
        self.assertEqual(normalize_paper_id("10.1038/s41586-024-001"), "doi:10.1038/s41586-024-001")
        self.assertEqual(normalize_paper_id("arXiv:2401.12345v2"), "arxiv:2401.12345v2")
        self.assertEqual(normalize_paper_id("https://arxiv.org/abs/2305.99999"), "arxiv:2305.99999")
        self.assertTrue(normalize_paper_id("Photonic Thermal Dissipation").startswith("paper:photonic-thermal-dissipation"))

    def test_thematic_clustering_deterministic_partitions(self):
        papers = [
            # Cluster 1: Silicon photonics & optical waveguides
            {"id": "p1", "title": "Co-Packaged Optics and Silicon Photonics", "abstract": "Micro-ring resonators reduce thermal dissipation and SerDes energy in datacenters."},
            {"id": "p2", "title": "Optical Waveguide Interconnect Transmission", "abstract": "Silicon photonic optical links demonstrate low propagation loss and reduced resistive heating."},
            {"id": "p3", "title": "Thermal Management in Photonic Integrated Circuits", "abstract": "Active micro-heater tuning mitigates temperature drift in optical resonators."},
            # Cluster 2: Perovskite solar cells
            {"id": "p4", "title": "Perovskite Tandem Solar Cell Efficiency", "abstract": "Monolithic perovskite-silicon tandem cells achieve high photovoltaic power conversion efficiency."},
            {"id": "p5", "title": "Bandgap Engineering in Perovskite Photovoltaics", "abstract": "Halide perovskite composition tuning optimizes photon absorption spectra."},
        ]

        clusters, p_to_c, cohesions = compute_thematic_clusters(papers, n_clusters=2)
        self.assertEqual(len(clusters), 2)
        self.assertEqual(len(p_to_c), 5)

        # Ensure photonics papers are grouped together and solar papers are grouped together
        c_photonics = p_to_c["p1"]
        self.assertEqual(p_to_c["p2"], c_photonics)
        self.assertEqual(p_to_c["p3"], c_photonics)

        c_solar = p_to_c["p4"]
        self.assertEqual(p_to_c["p5"], c_solar)
        self.assertNotEqual(c_photonics, c_solar)

        # Check cluster fields
        for c in clusters:
            self.assertGreaterEqual(len(c.keywords), 1)
            self.assertGreater(c.cohesion_score, 0.0)
            self.assertIsNotNone(c.seminal_paper_id)
            self.assertIn("centered on", c.summary)

    def test_thematic_clustering_edge_cases(self):
        # Empty list
        clusters, p_to_c, cohesions = compute_thematic_clusters([])
        self.assertEqual(len(clusters), 0)
        self.assertEqual(len(p_to_c), 0)

        # Single paper
        single = [{"id": "single-1", "title": "Quantum Entanglement Verification", "abstract": "Bell state test"}]
        clusters, p_to_c, cohesions = compute_thematic_clusters(single)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0].size, 1)
        self.assertEqual(clusters[0].cohesion_score, 1.0)
        self.assertEqual(p_to_c["single-1"], "cluster-1")

    def test_citation_network_graph_centrality_and_bridge_scores(self):
        papers = [
            {"id": "seed-1", "title": "Foundational Photonics", "abstract": "Optics baseline.", "cites": ["p-bridge"], "cited_by": []},
            {"id": "p-bridge", "title": "Optoelectronic Interfacial Physics", "abstract": "Bridge connecting photonic waveguides and photovoltaic collectors.", "cites": ["solar-1"], "cited_by": ["seed-1"]},
            {"id": "solar-1", "title": "Photovoltaic Light Trapping", "abstract": "Solar efficiency.", "cites": [], "cited_by": ["p-bridge"]},
            {"id": "leaf-1", "title": "Peripheral Optical Sensor", "abstract": "Sensor calibration.", "cites": ["seed-1"], "cited_by": []},
        ]
        clusters = [
            ThematicCluster(cluster_id="cluster-1", name="Photonic Optics", summary="Optics", keywords=["photonics"], paper_ids=["seed-1", "leaf-1"], size=2),
            ThematicCluster(cluster_id="cluster-2", name="Solar Energy", summary="Solar", keywords=["solar"], paper_ids=["solar-1"], size=1),
            ThematicCluster(cluster_id="cluster-3", name="Interfacial Physics", summary="Interface", keywords=["interface"], paper_ids=["p-bridge"], size=1),
        ]
        p_to_c = {"seed-1": "cluster-1", "leaf-1": "cluster-1", "solar-1": "cluster-2", "p-bridge": "cluster-3"}

        nodes, edges, bridges, structural_holes, density, components = compute_citation_network_metrics(
            papers, clusters, p_to_c
        )

        self.assertGreater(len(nodes), 0)
        self.assertGreater(len(edges), 0)
        self.assertIn("p-bridge", bridges)

        bridge_node = next(n for n in nodes if n.id == "p-bridge")
        leaf_node = next(n for n in nodes if n.id == "leaf-1")
        self.assertTrue(bridge_node.is_bridge)
        self.assertGreater(bridge_node.bridge_score, leaf_node.bridge_score)

    def test_structural_holes_detection(self):
        papers = [
            {"id": "c1-a", "title": "Neural Memory Networks", "abstract": "Memory retention."},
            {"id": "c1-b", "title": "Hopfield Energy Minimization", "abstract": "Energy landscapes."},
            {"id": "c2-a", "title": "Quantum Spin Glasses", "abstract": "Disordered magnetic systems."},
            {"id": "c2-b", "title": "Ising Model Optimization", "abstract": "Combinatorial physics."},
        ]
        clusters = [
            ThematicCluster(cluster_id="cluster-1", name="Neural Memory", summary="Memory", keywords=["memory", "energy"], paper_ids=["c1-a", "c1-b"], size=2),
            ThematicCluster(cluster_id="cluster-2", name="Statistical Physics", summary="Physics", keywords=["physics", "energy"], paper_ids=["c2-a", "c2-b"], size=2),
        ]
        p_to_c = {"c1-a": "cluster-1", "c1-b": "cluster-1", "c2-a": "cluster-2", "c2-b": "cluster-2"}

        nodes, edges, bridges, holes, density, components = compute_citation_network_metrics(
            papers, clusters, p_to_c
        )
        self.assertGreaterEqual(len(holes), 1)
        self.assertEqual(holes[0].citation_bridge_count, 0)
        self.assertIn("Unbridged epistemic gap", holes[0].research_opportunity)

    def test_2d_layout_and_mermaid_generation(self):
        papers = [
            {"id": "pA", "title": "Study Alpha", "citation_count": 12, "prisma_disposition": "INCLUDED"},
            {"id": "pB", "title": "Study Beta", "citation_count": 5, "prisma_disposition": "CANDIDATE", "cites": ["pA"]},
        ]
        clusters = [
            ThematicCluster(cluster_id="cluster-1", name="Core Theme", summary="Core", keywords=["alpha", "beta"], paper_ids=["pA", "pB"], size=2),
        ]
        p_to_c = {"pA": "cluster-1", "pB": "cluster-1"}

        nodes, edges, bridges, holes, density, components = compute_citation_network_metrics(
            papers, clusters, p_to_c
        )
        for n in nodes:
            self.assertIsInstance(n.x, float)
            self.assertIsInstance(n.y, float)
            self.assertGreaterEqual(n.x, -100.0)
            self.assertLessEqual(n.x, 100.0)

        graph = LiteratureCitationGraph(review_id="rev-test", nodes=nodes, edges=edges, clusters=clusters)
        mermaid = generate_citation_network_mermaid(graph)
        self.assertTrue(mermaid.startswith("graph TD"))
        self.assertIn("subgraph cluster-1", mermaid)
        self.assertIn("classDef bridge", mermaid)

    def test_end_to_end_clustering_and_graph_persistence(self):
        rev_id = "rev_phase7_test"
        save_prisma_review_db({
            "review_id": rev_id,
            "project_id": "proj_p7",
            "brief_id": "brief_p7",
            "title": "Empirical Review of High-Density Optical Interconnects",
            "status": "COMPLETED",
            "flow_counts": {"identified_total": 4, "included_studies": 2},
            "protocol": {"review_question": "Does CPO reduce thermal dissipation?"},
        }, db_path=self.db_path)

        # Add 3 screening decisions
        save_screening_decision_db({
            "decision_id": "dec-1",
            "review_id": rev_id,
            "source_url": "https://doi.org/10.1038/s41586-024-001",
            "title": "Co-Packaged Optics Micro-Ring Heat Dissipation",
            "rationale": "Optical interconnects achieve 0.85 pJ/bit vs 4.2 pJ/bit for copper SerDes.",
            "stage": "FULL_TEXT_ELIGIBILITY",
            "disposition": "INCLUDED",
        }, db_path=self.db_path)

        save_screening_decision_db({
            "decision_id": "dec-2",
            "review_id": rev_id,
            "source_url": "https://doi.org/10.1109/JSTQE.2024.002",
            "title": "Thermal Tuning Bottlenecks in Silicon Resonators",
            "rationale": "Micro-heater closed-loop tuning consumes 8 mW per channel, degrading net system efficiency.",
            "stage": "FULL_TEXT_ELIGIBILITY",
            "disposition": "INCLUDED",
        }, db_path=self.db_path)

        save_screening_decision_db({
            "decision_id": "dec-3",
            "review_id": rev_id,
            "source_url": "https://doi.org/10.1109/JSSC.2024.003",
            "title": "Cryogenic CMOS Driver Architecture for Superconducting Qubits",
            "rationale": "Low-power 4 Kelvin cryo-CMOS driver IC dissipating under 1.2 mW per control line.",
            "stage": "FULL_TEXT_ELIGIBILITY",
            "disposition": "INCLUDED",
        }, db_path=self.db_path)

        # Run clustering
        res = run_literature_clustering_and_graph(review_id=rev_id, db_path=self.db_path)
        self.assertGreaterEqual(res.total_papers, 2)
        self.assertGreaterEqual(res.num_clusters, 1)

        # Verify DB records
        c_db = get_literature_clustering_db(rev_id, db_path=self.db_path)
        self.assertIsNotNone(c_db)
        self.assertEqual(c_db["review_id"], rev_id)

        g_db = get_citation_graph_db(rev_id, db_path=self.db_path)
        self.assertIsNotNone(g_db)
        self.assertEqual(g_db["review_id"], rev_id)
        self.assertGreaterEqual(len(g_db["nodes"]), 2)

    # ==========================================================================
    # Deliverable B: Journal Formatter & Submission Engine Tests
    # ==========================================================================

    def test_preset_catalog_and_metadata(self):
        self.assertEqual(len(PRESET_CATALOG), 4)
        for preset in JournalPreset:
            meta = PRESET_CATALOG[preset]
            self.assertEqual(meta.preset, preset)
            self.assertIn("\\documentclass", meta.documentclass)
            self.assertGreater(len(meta.guidelines_summary), 10)

    def test_acm_latex_generation_and_anonymization(self):
        rev = {
            "title": "Quantum Photonics Optimization",
            "sections": {
                "abstract": {"heading": "Abstract", "content": "This study analyzes optical interconnects."},
                "introduction": {"heading": "Introduction", "content": "Photonic waveguides eliminate resistive losses."},
            },
            "references": [
                {"citation_key": "smith2024", "title": "Optical SerDes", "authors": ["A. Smith"], "year": 2024}
            ]
        }

        # Regular
        latex, meta = generate_acm_latex(rev, anonymize=False)
        self.assertIn("\\documentclass[sigconf]{acmart}", latex)
        self.assertIn("THOTH Research Engine", latex)
        self.assertIn("\\begin{CCSXML}", latex)
        self.assertIn("\\keywords{", latex)
        self.assertIn("\\bibitem{smith2024}", latex)

        # Anonymized
        latex_anon, _ = generate_acm_latex(rev, anonymize=True)
        self.assertIn("\\documentclass[sigconf,anonymous]{acmart}", latex_anon)
        self.assertIn("Anonymous Author(s)", latex_anon)
        self.assertNotIn("research@thoth.intellect", latex_anon)

    def test_ieee_latex_generation(self):
        rev = {
            "title": "High-Efficiency Silicon Laser Coupling",
            "sections": {
                "abstract": {"heading": "Abstract", "content": "Low-loss optical coupling is critical for CPO."},
                "results": {"heading": "Experimental Results", "content": "Coupling losses remained under 0.8 dB."},
            },
            "references": [{"citation_key": "wang2025", "title": "Sub-Micron Alignment", "authors": ["B. Wang"], "year": 2025}]
        }
        latex, _ = generate_ieee_latex(rev, anonymize=False)
        self.assertIn("\\documentclass[conference]{IEEEtran}", latex)
        self.assertIn("\\begin{IEEEkeywords}", latex)
        self.assertIn("\\IEEEauthorblockN{THOTH Research Engine}", latex)
        self.assertIn("wang2025", latex)

    def test_nature_latex_methods_at_end(self):
        rev = {
            "title": "Room-Temperature Superconductivity Verification",
            "sections": {
                "abstract": {"heading": "Abstract", "content": "Replication attempts under diamond anvil cell pressure."},
                "methodology": {"heading": "High-Pressure Synthesis Methods", "content": "Laser-heated diamond anvil cells were maintained at 150 GPa."},
                "discussion": {"heading": "Discussion", "content": "No zero-resistance transition was observed."},
            },
            "references": [{"citation_key": "nature_ref1", "title": "Hydride Superconductors", "authors": ["C. Lee"], "year": 2023}]
        }
        latex, _ = generate_nature_latex(rev, anonymize=False)
        self.assertIn("\\documentclass[default,iicol]{sn-jnl}", latex)
        self.assertIn("\\abstract{", latex)

        # Verify Methods appears AFTER discussion and references in the LaTeX output
        pos_disc = latex.find("\\section{Discussion}")
        pos_methods = latex.find("\\section{High-Pressure Synthesis Methods}")
        self.assertGreater(pos_methods, pos_disc, "Methods section must appear at the end for Nature formatting")

    def test_neurips_latex_and_paper_checklist(self):
        rev = {
            "title": "Empirical Scaling Laws for Deep Entailment Verifiers",
            "sections": {
                "abstract": {"heading": "Abstract", "content": "Analyzing scaling regimes of formal verification."},
                "experiments": {"heading": "Empirical Verification", "content": "Tested on 10,000 adversarial claims."},
            },
            "references": []
        }
        latex, _ = generate_neurips_latex(rev, anonymize=True)
        self.assertIn("neurips_2024", latex)
        self.assertIn("Anonymous Author(s)", latex)
        self.assertIn("NeurIPS Paper Checklist", latex)
        self.assertIn("\\item \\textbf{Claims}", latex)
        self.assertIn("\\item \\textbf{Reproducibility}", latex)

    def test_submission_checklist_generation(self):
        rev = {
            "sections": {
                "abstract": {"content": " ".join(["word"] * 150)},
                "intro": {"content": " ".join(["content"] * 800)},
            },
            "references": [{"doi": "10.1000/182", "year": 2024}],
            "claims": [{"evidence_status": "SUPPORTED"}],
        }
        checklist = generate_submission_checklist(JournalPreset.ACM, rev, anonymize=True)
        self.assertIn("ACM Conference Proceedings", checklist)
        self.assertIn("Abstract word count", checklist)
        self.assertIn("Double-Blind Anonymization", checklist)
        self.assertIn("Bibliographic Integrity", checklist)

    def test_journal_submission_package_zip_bundling(self):
        proj_id = "proj_p7"
        save_project_db(
            project_id=proj_id,
            title="Project P7 Bundle",
            db_path=self.db_path,
        )
        ms_id = "ms_bundle_test"
        save_manuscript_db(
            manuscript_id=ms_id,
            project_id=proj_id,
            title="Quantum Waveguide Coherence",
            current_version=1,
            db_path=self.db_path,
        )

        save_manuscript_revision_db(
            revision_id="rev_ms_bundle_1",
            manuscript_id=ms_id,
            version=1,
            title="Quantum Waveguide Coherence",
            sections={
                "abstract": {"heading": "Abstract", "content": "Decoherence mitigation in silicon waveguides."},
                "results": {"heading": "Results", "content": "99.8% coherence preserved across 10 cm chip path."},
            },
            references=[
                {
                    "citation_key": "ref1",
                    "title": "Coherence Physics",
                    "authors": ["X. Zhang"],
                    "year": 2025,
                    "journal": "IEEE Trans. Quantum Eng.",
                    "doi": "10.1109/TQE.2025.001",
                }
            ],
            claims=[
                {"claim_id": "c1", "evidence_status": "SUPPORTED", "claim_text": "99.8% coherence preserved."}
            ],
            db_path=self.db_path,
        )

        pkg = build_journal_submission_package(
            manuscript_id=ms_id,
            preset_name="acm",
            version=1,
            anonymize=True,
            db_path=self.db_path,
        )

        self.assertIn("pkg_acm_", pkg["package_id"])
        self.assertIn("\\documentclass[sigconf,anonymous]{acmart}", pkg["latex_content"])
        self.assertIn("@article", pkg["bibtex_content"])
        self.assertGreater(pkg["file_size_bytes"], 100)

        # Inspect ZIP buffer
        import base64
        zip_bytes = base64.b64decode(pkg["zip_base64"])
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            namelist = zf.namelist()
            self.assertIn("manuscript.tex", namelist)
            self.assertIn("references.bib", namelist)
            self.assertIn("SUBMISSION_CHECKLIST.md", namelist)
            self.assertIn("manuscript.pdf", namelist)
            self.assertIn("MANIFEST.json", namelist)

        # Check DB persistence
        sub_db = get_journal_submission_db(pkg["package_id"], db_path=self.db_path)
        self.assertIsNotNone(sub_db)
        self.assertEqual(sub_db["preset"], "acm")
        self.assertEqual(sub_db["is_anonymized"], 1)

    # ==========================================================================
    # Deliverable C: REST API Integration Tests
    # ==========================================================================

    def test_rest_api_clustering_endpoints(self):
        rev_id = "rev_api_test"
        save_prisma_review_db({
            "review_id": rev_id,
            "project_id": "proj_api",
            "brief_id": "brief_api_1",
            "title": "API Literature Clustering Test",
        }, db_path=self.db_path)

        save_screening_decision_db({
            "decision_id": "dec-api-1",
            "review_id": rev_id,
            "source_url": "https://doi.org/10.1038/api-paper-1",
            "title": "Co-Packaged Optical Interconnects",
            "rationale": "Energy dissipation in CPO systems and waveguides.",
            "disposition": "INCLUDED",
        }, db_path=self.db_path)

        save_screening_decision_db({
            "decision_id": "dec-api-2",
            "review_id": rev_id,
            "source_url": "https://doi.org/10.1038/api-paper-2",
            "title": "Silicon Photonics Advanced Packaging",
            "rationale": "Packaging thermal limits in optical transceivers.",
            "disposition": "INCLUDED",
        }, db_path=self.db_path)

        save_screening_decision_db({
            "decision_id": "dec-api-3",
            "review_id": rev_id,
            "source_url": "https://doi.org/10.1038/api-paper-3",
            "title": "Superconducting Qubit Control",
            "rationale": "Cryogenic control lines and dilution refrigerators.",
            "disposition": "INCLUDED",
        }, db_path=self.db_path)

        # 1. POST cluster
        res = self.client.post(
            f"/api/prisma/reviews/{rev_id}/cluster?db_path={self.db_path}",
            json={"n_clusters": 2}
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("clustering", data)

        # 2. GET cluster
        res_get = self.client.get(f"/api/prisma/reviews/{rev_id}/cluster?db_path={self.db_path}")
        self.assertEqual(res_get.status_code, 200)

        # 3. GET citation graph
        res_graph = self.client.get(f"/api/prisma/reviews/{rev_id}/citation-graph?db_path={self.db_path}")
        self.assertEqual(res_graph.status_code, 200)
        self.assertIn("citation_graph", res_graph.json())

        # 4. GET citation graph mermaid
        res_mermaid = self.client.get(f"/api/prisma/reviews/{rev_id}/citation-graph/mermaid?db_path={self.db_path}")
        self.assertEqual(res_mermaid.status_code, 200)
        self.assertIn("graph TD", res_mermaid.json()["mermaid"])

    def test_rest_api_journal_submission_endpoints(self):
        # 1. List presets
        res_presets = self.client.get("/api/manuscripts/journal-presets")
        self.assertEqual(res_presets.status_code, 200)
        presets = res_presets.json()["presets"]
        self.assertEqual(len(presets), 4)

        # 2. Setup project and manuscript
        proj_id = "proj_journal_api"
        save_project_db(
            project_id=proj_id,
            title="Project Journal API",
            db_path=self.db_path,
        )
        ms_id = "ms_journal_api"
        save_manuscript_db(
            manuscript_id=ms_id,
            project_id=proj_id,
            title="Photonic Memory Subsystems",
            current_version=1,
            db_path=self.db_path,
        )
        save_manuscript_revision_db(
            revision_id="rev_ms_journal_api_1",
            manuscript_id=ms_id,
            version=1,
            title="Photonic Memory Subsystems",
            sections={"abstract": {"heading": "Abstract", "content": "Optical memory cells."}},
            references=[{"citation_key": "ref_api", "title": "Memory", "year": 2024}],
            db_path=self.db_path,
        )

        # 3. POST journal submission package
        res_pkg = self.client.post(
            f"/api/manuscripts/{ms_id}/journal-submission?db_path={self.db_path}",
            json={"preset": "ieee", "version": 1, "anonymize": False}
        )
        self.assertEqual(res_pkg.status_code, 200)
        pkg_data = res_pkg.json()["submission"]
        sub_id = pkg_data["package_id"]
        self.assertIn("pkg_ieee_", sub_id)

        # 4. GET list submissions for manuscript
        res_list = self.client.get(f"/api/manuscripts/{ms_id}/journal-submissions?db_path={self.db_path}")
        self.assertEqual(res_list.status_code, 200)
        self.assertEqual(len(res_list.json()["submissions"]), 1)

        # 5. GET submission details
        res_detail = self.client.get(f"/api/submissions/{sub_id}?db_path={self.db_path}")
        self.assertEqual(res_detail.status_code, 200)

        # 6. GET download submission zip
        res_dl = self.client.get(f"/api/submissions/{sub_id}/download?db_path={self.db_path}")
        self.assertEqual(res_dl.status_code, 200)
        self.assertEqual(res_dl.headers["content-type"], "application/zip")

        # 7. GET project literature map
        res_litmap = self.client.get(f"/api/projects/{proj_id}/literature-map?db_path={self.db_path}")
        self.assertEqual(res_litmap.status_code, 200)
        self.assertEqual(res_litmap.json()["literature_map"]["project_id"], proj_id)


if __name__ == "__main__":
    unittest.main()
