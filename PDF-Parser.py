import PyPDF2
from openai import OpenAI


def pdf_to_text(file_path):
    # Open the PDF file in binary mode
    with open(file_path, "rb") as file:
        # Create a PDF file reader object
        pdf_reader = PyPDF2.PdfReader(file)

        # Initialize an empty string to store the text
        text = ""

        # Loop through each page in the PDF
        for page in pdf_reader.pages:
            # Extract the text from the page
            text += page.extract_text()

    return text


# Calls OpenAI API to summarize the text
def send_chat(resume_text):
    openai = OpenAI()
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo-1106",
        response_format={ "type": "json_object" },
        messages=[
            {"role": "system", "content": "You are an AI assistant helping summarize resume, designed to output JSON."},
            {"role": "user", "content": resume_text}]
    )
    # print(response)
    return response.choices[0].message.content


if __name__ == "__main__":
    file_path = "functionalsample.pdf"
    response = send_chat(pdf_to_text(file_path))
    print(response)