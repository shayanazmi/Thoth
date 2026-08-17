import unittest
from unittest.mock import patch
from backend.agents import CriticScore, critic_chain
from backend.pipeline import critic_node, ResearchState
from langchain_core.runnables import RunnableSequence


class TestCriticScoreAndNode(unittest.TestCase):
    def test_critic_score_pydantic_validation(self):
        valid_dict = {
            "faithfulness": 9.0,
            "relevance": 8.5,
            "completeness": 9.5,
            "evidence_quality": 8.0,
            "clarity_and_coherence": 9.0,
            "overall_score": 8.8,
            "strengths": ["Well researched", "Clear structure"],
            "areas_to_improve": ["Add more citations"],
            "verdict": "High quality report.",
            "reasoning": "Detailed analysis backed by solid sources."
        }
        score_obj = CriticScore(**valid_dict)
        self.assertEqual(score_obj.overall_score, 8.8)
        self.assertEqual(len(score_obj.strengths), 2)

    @patch.object(RunnableSequence, "invoke")
    def test_critic_node_success(self, mock_invoke):
        mock_invoke.return_value = {
            "faithfulness": 9.0,
            "relevance": 9.0,
            "completeness": 9.0,
            "evidence_quality": 9.0,
            "clarity_and_coherence": 9.0,
            "overall_score": 9.0,
            "strengths": ["Great depth"],
            "areas_to_improve": ["None"],
            "verdict": "Ready for publication.",
            "reasoning": "Excellent report."
        }
        state: ResearchState = {
            "topic": "AI Testing",
            "report": "Sample report text",
            "role": "", "tone": "", "language": "", "scrape_top_n": 2, "min_score": 6.5,
            "max_retries": 2, "attempt": 1, "search_results": "", "scraped_content": "",
            "feedback": "", "verifier_feedback": "", "score": 0.0, "follow_up_questions": [],
            "mindmap": {"nodes": [], "edges": []}, "cumulative_sources": [],
            "conversation_summary": "", "chat_turns": []
        }
        res = critic_node(state)
        self.assertEqual(res["score"], 9.0)
        self.assertIn("**Overall** | **9.0**", res["feedback"])

    @patch.object(RunnableSequence, "invoke")
    def test_critic_node_loud_error_on_invalid_json(self, mock_invoke):
        # Corrupted response missing overall_score and fields
        mock_invoke.return_value = {"invalid_field": "bad content"}

        state: ResearchState = {
            "topic": "AI Testing",
            "report": "Sample report text",
            "role": "", "tone": "", "language": "", "scrape_top_n": 2, "min_score": 6.5,
            "max_retries": 2, "attempt": 1, "search_results": "", "scraped_content": "",
            "feedback": "", "verifier_feedback": "", "score": 0.0, "follow_up_questions": [],
            "mindmap": {"nodes": [], "edges": []}, "cumulative_sources": [],
            "conversation_summary": "", "chat_turns": []
        }

        with self.assertRaises(ValueError) as cm:
            critic_node(state)
        
        self.assertIn("Failed to parse structured CriticScore", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
