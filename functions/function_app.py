import PyPDF2
import logging
import os
import json
import uuid
import io
import logging
from datetime import datetime, timezone
from openai import OpenAI
import azure.functions as func
import azure.cosmos.documents as documents
import azure.cosmos.cosmos_client as cosmos_client
import azure.cosmos.exceptions as exceptions
from azure.cosmos.partition_key import PartitionKey
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient


# logger=logging.getLogger(__name__)
# logger.setLevel(logging.INFO)


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
                "content": """
                You are an AI assistant helping summarize resumes, designed to output JSON. You accurately summarize the resume into JSON format using the following as a guide. 
{
"general_info": {
"name": "John Doe",
"address": "123 Main St, Anytown, USA",
"phone": "(123) 456-7890",
"email": "johndoe@example.com"
},
"work_history": [
{
"position": "Software Engineer",
"company_name": "Company A",
"start_date": "2015-06-01",
"end_date": "2019-05-31"
},
{
"position": "Senior Software Engineer",
"company_name": "Company B",
"start_date": "2019-06-01",
"end_date": "2023-05-31"
}
],
"experience": [
{
"role": "Software Engineer",
"description": "Developed web applications",
"organization": "Company A"
},
{
"role": "Volunteer Teacher",
"description": "Taught basic programming to high school students",
"organization": "Education Foundation"
}
],
"education": [
{
"institution_name": "University X",
"start_date": "2011-08-01",
"end_date": "2015-05-31",
"certificate_degree": "Bachelor of Science in Computer Science"
}
],
"skills": [
{
"skill_name": "Python",
"skill_level": "Expert"
},
{
"skill_name": "JavaScript",
"skill_level": "Not Specified"
},
{
"skill_name": "React",
"skill_level": "4 years"
}
]
}
"""
            },
            {"role": "user", "content": resume_text},
        ],
    )
    return json.loads(response.choices[0].message.content)


# Creates a new item in the Cosmos DB container
def add_resume_to_cosmos(container, contents, uri):
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

def store_resume_text_in_blob(blob_service_client, text):
    blob_client = blob_service_client.get_blob_client("resumetext",
                                                      "consolidated_resumes.txt")
    blob_client.append_block(text)

# Receive PDF from HTTP request
@app.function_name("receivePDF")
@app.route(route="receivePDF", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def receive_pdf(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("receive_pdf(): Receiving a PDF file. ")

    # Check if req.files is not None
    if "fileToUpload" not in req.files or req.files["fileToUpload"] is None:
        return func.HttpResponse(
            "receive_pdf(): No file found in the request under the name 'fileToUpload'",
            status_code=400,
        )

    # Try except block to catch any exceptions
    try:
        # Get the file from the request
        file = req.files["fileToUpload"].stream.read()
        # Get the filename
        filename = datetime.now().isoformat() + "_" + req.files["fileToUpload"].filename
    except Exception as e:
        return func.HttpResponse(
            f"receive_pdf(): An error occurred while reading the file: {e}",
            status_code=500,
        )

    # Check if os.environ["bcpdfparser_STORAGE"] is not None
    if "bcpdfparser_STORAGE" not in os.environ:
        return func.HttpResponse(
            "receive_pdf(): The environment variable 'bcpdfparser_STORAGE' is not set.",
            status_code=500,
        )

    # Initialize the Blob Service client
    blob_service_client = BlobServiceClient.from_connection_string(
        os.environ["bcpdfparser_STORAGE"]
    )

    try:
        # Push pdf to blob storage
        blob_client = blob_service_client.get_blob_client("resumes", filename)
        blob_client.upload_blob(file)
    except Exception as e:
        return error_handler(
            "receive_pdf(): An error occurred while uploading the file to blob storage", 500, e)

    return func.HttpResponse(f"File {filename} has been received and saved.")


@app.blob_trigger(arg_name="myblob", path="resumes", connection="bcpdfparser_STORAGE")
def pdf_loader(myblob: func.InputStream):
    # Check if myblob is not None
    if myblob is None:
        return func.HttpResponse("pdf_loader(): No blob found in the request.", status_code=400)

    # Try except block to catch any exceptions
    try:
        # Read the entire PDF into file
        file = myblob.read(size=-1)
    except Exception as e:
        return error_handler("pdf_loader(): An error occurred while reading the blob", 500, e)

    # Check if file is not None
    if file is None:
        return error_handler("pdf_loader(): No file found in the blob.", 400)
    
    # Create a file-like object from the file
    f = io.BytesIO(file)

    try:
        # Create a PDF reader using the file-like object
        mydoc = PyPDF2.PdfReader(f)
        # Initialize an empty string to store the text
        text = ""
    except Exception as e:
        return error_handler("An error occurred while reading the PDF", 500, e)


    try:
        # Initialize the Cosmos DB client
        client = cosmos_client.CosmosClient(
            HOST,
            {"masterKey": MASTER_KEY},
            user_agent="PDFParser",
            user_agent_overwrite=True,
        )
        db = client.get_database_client(DATABASE_ID)
        container = db.get_container_client(CONTAINER_ID)
    except Exception as e:
        return error_handler("pdf_loader(): An error occurred while initializing the Cosmos DB client", 500, e)

    blob_connection_string = os.environ["bcpdfparser_STORAGE"]
    if blob_connection_string is None:
        return error_handler("pdf_loader(): The bcpdfparser_STORAGE is not defined.", 500)
    
    # Initialize the Blob Service client
    blob_service_client = BlobServiceClient.from_connection_string(blob_connection_string)

    if mydoc.pages is None:
        return error_handler("pdf_loader(): No pages found in the PDF.", 400)
    
    # Loop through each page in the PDF
    for page in mydoc.pages:
        # Extract the text from the page
        text += page.extract_text()

    try:
        # Call the send_chat function to summarize the text
        response = send_chat(text)
    except Exception as e:
        return error_handler("An error occurred while summarizing the text using GPT", 500, e)
    
    # Move the blob to the processed container
    try:
        uri = move_blob(blob_service_client, myblob, "processed")
    except Exception as e:
        return error_handler("An error occurred while moving the blob to the processed container", 500, e)
    try:
        store_resume_text_in_blob(blob_service_client, text)
    except Exception as e:
        return error_handler("An error occurred while moving the blob to the processed container", 500, e)
    
    try:
        add_resume_to_cosmos(container, response, uri)
    except Exception as e:
        return error_handler("An error occurred while creating the item in the Cosmos DB container", 500, e)

def error_handler(message, status_code, exception=None):
    logging.error(message + " " + str(exception) if exception else "")
    return func.HttpResponse(message, status_code = status_code)

@app.function_name("summarizePDF")
@app.route(route="summarizePDF", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def summarizePDF(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("summarizePDF(): Receiving a PDF file. ")

    # Check if req.files is not None
    if "fileToUpload" not in req.files or req.files["fileToUpload"] is None:
        return func.HttpResponse(
            "summarizePDF(): No file found in the request under the name 'fileToUpload'",
            status_code=400,
        )

    # Try except block to catch any exceptions
    try:
        # Get the file from the request
        file = req.files["fileToUpload"].stream.read()
        # Get the filename
        filename = datetime.now().isoformat() + "_" + req.files["fileToUpload"].filename
    except Exception as e:
        return func.HttpResponse(
            f"summarizePDF(): An error occurred while reading the file: {e}",
            status_code=500,
        )
    
    # Create a file-like object from the file
    f = io.BytesIO(file)

    try:
        # Create a PDF reader using the file-like object
        mydoc = PyPDF2.PdfReader(f)
        # Initialize an empty string to store the text
        text = ""
    except Exception as e:
        return error_handler("An error occurred while reading the PDF", 500, e)


    if mydoc.pages is None:
        return error_handler("pdf_loader(): No pages found in the PDF.", 400)
    
    # Loop through each page in the PDF
    for page in mydoc.pages:
        # Extract the text from the page
        text += page.extract_text()

    try:
        # Call the send_chat function to summarize the text
        response = send_chat(text)
    except Exception as e:
        return error_handler("An error occurred while summarizing the text using GPT", 500, e)

    return func.HttpResponse(f"{response}")

