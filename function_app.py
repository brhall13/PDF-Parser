import PyPDF2
from openai import OpenAI
import azure.functions as func
import io

app = func.FunctionApp()

# Calls OpenAI API to summarize the text
def send_chat(resume_text):
    openai = OpenAI()
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo-1106",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": "You are an AI assistant helping summarize resume, designed to output JSON.",
            },
            {"role": "user", "content": resume_text},
        ],
    )
    # print(response)
    return response.choices[0].message.content


@app.blob_trigger(arg_name="myblob", path="resumes", connection="bcpdfparser_STORAGE")
def pdf_loader(myblob: func.InputStream):
    file = myblob.read(size=-1)
    f = io.BytesIO(file)
    mydoc = PyPDF2.PdfReader(f)
    # Initialize an empty string to store the text
    text = ""

    # Loop through each page in the PDF
    for page in mydoc.pages:
        # Extract the text from the page
        text += page.extract_text()
    # print(text)
    send_chat(text)