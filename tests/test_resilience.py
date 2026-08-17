import unittest
from unittest.mock import patch, MagicMock
import requests
from backend.tools import scrape_url, _scrape_url_with_retry
from backend.agents import FallbackLLMWrapper
from langchain_core.messages import AIMessage


class TestNetworkAndLLMResilience(unittest.TestCase):

    @patch("requests.get")
    def test_scrape_url_retries_on_503(self, mock_get):
        # First 2 attempts return 503, 3rd attempt succeeds
        resp_503 = MagicMock()
        resp_503.status_code = 503
        resp_503.raise_for_status.side_effect = requests.exceptions.RequestException("HTTP 503")

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.text = "<html><body><p>Scraped content successfully.</p></body></html>"
        resp_200.raise_for_status.return_value = None

        mock_get.side_effect = [resp_503, resp_503, resp_200]

        result = scrape_url.invoke("https://example.com/test")
        self.assertIn("Scraped content successfully", result)
        self.assertEqual(mock_get.call_count, 3)

    @patch("requests.get")
    def test_scrape_url_fails_gracefully_after_3_attempts(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection Refused")

        result = scrape_url.invoke("https://example.com/fail")
        self.assertIn("Could not scrape URL", result)
        self.assertEqual(mock_get.call_count, 3)

    def test_fallback_llm_wrapper_primary_success(self):
        primary_mock = MagicMock()
        primary_mock.invoke.return_value = AIMessage(content="Primary response")
        fallback_mock = MagicMock()

        wrapper = FallbackLLMWrapper(
            primary_llm=primary_mock,
            fallback_llm=fallback_mock,
            primary_name="PrimaryTest",
            fallback_name="FallbackTest"
        )

        res = wrapper.invoke("hello")
        self.assertEqual(res.content, "Primary response")
        primary_mock.invoke.assert_called_once()
        fallback_mock.invoke.assert_not_called()

    def test_fallback_llm_wrapper_fallback_on_primary_failure(self):
        primary_mock = MagicMock()
        primary_mock.invoke.side_effect = Exception("500 Internal Server Error on NIM")
        fallback_mock = MagicMock()
        fallback_mock.invoke.return_value = AIMessage(content="Fallback response")

        wrapper = FallbackLLMWrapper(
            primary_llm=primary_mock,
            fallback_llm=fallback_mock,
            primary_name="PrimaryTest",
            fallback_name="FallbackTest"
        )

        res = wrapper.invoke("hello")
        self.assertEqual(res.content, "Fallback response")
        primary_mock.invoke.assert_called_once()
        fallback_mock.invoke.assert_called_once()


if __name__ == "__main__":
    unittest.main()
