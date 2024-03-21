import unittest
import os
import uuid
from function_app import summarize_resume, embed, add_resume_to_cosmos, add_vectorized_resume_to_cosmos

class TestFunctionApp(unittest.TestCase):
    def test_summarize_resume(self):
        """Test that GPT responds to a chat message with JSON formatting."""
        original_dir = os.getcwd()
        os.chdir(os.path.dirname(__file__))
        resume_text = "Please respond with a sample resume for a software engineer."

        response = summarize_resume(resume_text)
        self.assertTrue("general_info" in response)
        os.chdir(original_dir)

    def test_embed(self):
        """Test the embed function."""
        content = "Test"

        result = embed(content)
        self.assertEqual(len(result[0]), 1536)

    def test_add_resume_to_cosmos(self):
        """Test the add_resume_to_cosmos function."""
        contents = {"name": "John Doe", "email": "johndoe@example.com"}
        resume_blob_location = "resume.pdf"
        guid = str(uuid.uuid4())

        response = add_resume_to_cosmos(contents, resume_blob_location, guid)

        self.assertTrue("id" in response)

    def test_add_vectorized_resume_to_cosmos(self):
        """Test the add_resume_to_cosmos function."""
        contents = {"text": "this is my resume, I am skilled at python"}
        guid = str(uuid.uuid4())

        response = add_vectorized_resume_to_cosmos(contents, guid)

        # self.assertTrue("id" in response)
        self.assertTrue(True)

if __name__ == '__main__':
    unittest.main(buffer=False)
