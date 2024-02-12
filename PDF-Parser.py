import PyPDF2
from openai import OpenAI
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
import os
import logging
import argparse

load_dotenv()


def setup_logging(verbosity):
    if verbosity == 0:
        logging.basicConfig(level=logging.WARNING)
    elif verbosity == 1:
        logging.basicConfig(level=logging.INFO)
    elif verbosity >= 2:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

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


# GET FILE FROM AZURE STORAGE
account_url = "https://bcpdfparser.blob.core.windows.net"
default_credential = DefaultAzureCredential()

# Create the BlobServiceClient object
blob_service_client = BlobServiceClient(account_url, credential=default_credential)


def get_file_from_azurestorage(
    blob_service_client, container_name, blob_name, download_file_path
):
    blob_client = blob_service_client.get_blob_client(container_name, blob_name)

    with open(download_file_path, "wb") as download_file:
        download_file.write(blob_client.download_blob().readall())


# Usage
connection_string = os.getenv("CONNECTION_STRING")
blob_service_client = BlobServiceClient.from_connection_string(connection_string)
print(connection_string)

container_name = "resumes"
blob_name = "Abigail Carpentier Resume Sample.pdf"
download_file_path = "PDFS/" + blob_name

get_file_from_azurestorage(
    blob_service_client, container_name, blob_name, download_file_path
)

# Create a ContainerClient
container_client = blob_service_client.get_container_client(container_name)

# List the blobs in the container
blob_list = container_client.list_blobs()
for blob in blob_list:
    print(blob.name + "\n")

def main():
    parser = argparse.ArgumentParser(description="PDF Parser")
    parser.add_argument("-v", "--verbose", help="increase output verbosity",
                        action="count", default=0)
    args = parser.parse_args()
    setup_logging(args.verbose)
    # file_path = "functionalsample.pdf"
    # response = send_chat(pdf_to_text(file_path))
    # print(response)
    # get_file_from_azurestorage(blob_service_client, container_name, blob_name, download_file_path)
    for blob in blob_list:
        print(blob.name + "\n")
        get_file_from_azurestorage(
            blob_service_client, container_name, blob.name, download_file_path
        )
    get_file_from_azurestorage(
        blob_service_client, container_name, blob_name, download_file_path
    )

if __name__ == "__main__":
    main()

