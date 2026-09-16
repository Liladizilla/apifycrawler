import unittest

from actor import build_search_query, extract_social_links


class ActorSearchBehaviors(unittest.TestCase):
    def test_build_search_query_combines_destination_and_search_term(self):
        self.assertEqual(
            build_search_query("Nairobi", "hotel"),
            "hotel in Nairobi",
        )

    def test_extract_social_links_handles_common_platform_urls(self):
        html = '''
        <html>
          <body>
            <a href="https://facebook.com/examplepage">Facebook</a>
            <a href="https://instagram.com/examplepage">Instagram</a>
            <a href="https://x.com/examplepage">X</a>
            <a href="https://wa.me/254712345678">WhatsApp</a>
          </body>
        </html>
        '''
        result = extract_social_links(html)
        self.assertIn("https://facebook.com/examplepage", result["facebook"])
        self.assertIn("https://instagram.com/examplepage", result["instagram"])
        self.assertIn("https://x.com/examplepage", result["x"])
        self.assertIn("https://wa.me/254712345678", result["whatsapp"])


if __name__ == "__main__":
    unittest.main()
