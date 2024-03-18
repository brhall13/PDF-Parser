import unittest
from function_app import summarize_resume

class TestFunctionApp(unittest.TestCase):
    def test_send_chat(self):
        resume_text = "This is my resume text."
        expected_response = {
            "role": "assistant",
            "content": "This is the response from the chat model."
        }

        response = summarize_resume(resume_text)

        self.assertEqual(response, expected_response)

if __name__ == '__main__':
    unittest.main()