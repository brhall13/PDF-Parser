import PyPDF2
import logging
import os
import json
import uuid
import io
from openai import OpenAI
import azure.functions as func
import azure.cosmos.documents as documents
import azure.cosmos.cosmos_client as cosmos_client
import azure.cosmos.exceptions as exceptions
from azure.cosmos.partition_key import PartitionKey
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient

# Initialize the function app
app = func.FunctionApp()

# Set the environment variables 
HOST = os.getenv("ACCOUNT_HOST")
MASTER_KEY = os.getenv("ACCOUNT_KEY")
DATABASE_ID = os.getenv("COSMOS_DATABASE")
CONTAINER_ID = os.getenv("COSMOS_CONTAINER")


# Calls OpenAI API to summarize the text
def send_chat(resume_text):
    openai = OpenAI()
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo-1106",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": "You are an AI assistant helping summarize resumes, designed to output JSON.",
            },
            {"role": "user", "content": resume_text},
        ],
    )
    return json.loads(response.choices[0].message.content)


# Creates a new item in the Cosmos DB container
def create_item(container, contents, uri):
    print("\nUpserting an item\n")
    contents["id"] = str(uuid.uuid4())
    contents["resume_uri"] = uri

    response = container.create_item(body=contents)
    # print("Upserted Item's Id is {0}".format(response["id"]))


# Function to move a blob to a processed container
def move_blob(blob_service_client, resumes_blob, destination_container_name):
    # Get the source and destination blob clients
    source_blob = blob_service_client.get_blob_client(
        "resumes", resumes_blob.name.split("/")[-1]
    )
    destination_blob = blob_service_client.get_blob_client(
        destination_container_name, resumes_blob.name.split("/")[-1]
    )
    # Copy the blob from the source to the destination
    destination_blob.start_copy_from_url(resumes_blob.uri)
    # Delete the source blob
    source_blob.delete_blob()
    return destination_blob.url

# Receive PDF from HTTP request
@app.function_name('receivePDF')
@app.route(route='receivePDF', methods=['POST'], auth_level=func.AuthLevel.ANONYMOUS)
def receive_pdf(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    file = req.files['fileToUpload'].stream.read()
    filename = req.files['fileToUpload'].filename

    blob_service_client = BlobServiceClient.from_connection_string(
        os.environ["bcpdfparser_STORAGE"]
    )

    if not file:
        return func.HttpResponse(
             "No file found in the request",
             status_code=400
        )

    # Push pdf to blob storage
    blob_client = blob_service_client.get_blob_client("resumes", filename)
    blob_client.upload_blob(file)

    return func.HttpResponse(f"File {filename} has been received and saved.")


@app.blob_trigger(arg_name="myblob", path="resumes", connection="bcpdfparser_STORAGE")
def pdf_loader(myblob: func.InputStream):
    # Read the entire PDF into file
    file = myblob.read(size=-1)
    # Create a file-like object from the file
    f = io.BytesIO(file)
    # Create a PDF reader using the file-like object
    mydoc = PyPDF2.PdfReader(f)
    # Initialize an empty string to store the text
    text = ""

    # Initialize the Cosmos DB client
    client = cosmos_client.CosmosClient(
        HOST,
        {"masterKey": MASTER_KEY},
        user_agent="PDFParser",
        user_agent_overwrite=True,
    )
    db = client.get_database_client(DATABASE_ID)
    container = db.get_container_client(CONTAINER_ID)

    # Initialize the Blob Service client
    blob_service_client = BlobServiceClient.from_connection_string(
        os.environ["bcpdfparser_STORAGE"]
    )

    # Loop through each page in the PDF
    for page in mydoc.pages:
        # Extract the text from the page
        text += page.extract_text()
    response = send_chat(text)
    # Move the blob to the processed container
    uri = move_blob(blob_service_client, myblob, "processed")
    create_item(container, response, uri)
