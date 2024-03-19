import PyPDF2
import logging
import os
import json
import uuid
import io
import logging
from typing import List
from jinja2 import Template, Environment, FileSystemLoader
from datetime import datetime, timezone
import openai
import azure.functions as func
import azure.cosmos.documents as documents
import azure.cosmos.cosmos_client as cosmos_client
import azure.cosmos.exceptions as exceptions
from azure.cosmos.partition_key import PartitionKey
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
from pinecone import Pinecone
from dotenv import load_dotenv
# logger=logging.getLogger(__name__)
# logger.setLevel(logging.INFO)

# Initialize the function app
app = func.FunctionApp()

#load environment variables
load_dotenv()

env = Environment(loader=FileSystemLoader("templates"))

class Settings:
    # Initialize the environment variables
    blob_connection_string = os.environ["BC_PDF_PARSER_STORAGE"]
    blob_service_client = BlobServiceClient.from_connection_string(blob_connection_string)
    HOST = os.getenv("ACCOUNT_HOST")
    MASTER_KEY = os.getenv("ACCOUNT_KEY")
    DATABASE_ID = os.getenv("COSMOS_DATABASE")
    CONTAINER_ID = os.getenv("COSMOS_CONTAINER")
    VECTORIZED_CONTAINER_ID = CONTAINER_ID + "_vector"
    EMBEDDING_MODEL = "text-embedding-3-small"
    OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
    PINECONE_API_KEY = os.environ["PINECONE_API_KEY"]


    # Initialize the Cosmos DB client
    def get_cosmos_client():
        client = cosmos_client.CosmosClient(
            Settings.HOST,
            {"masterKey": Settings.MASTER_KEY},
            user_agent="PDFParser",
            user_agent_overwrite=True,
        )
        return client.create_database_if_not_exists(Settings.DATABASE_ID)

    @staticmethod
    def get_container():
        return Settings.get_cosmos_client().create_container_if_not_exists(
            Settings.CONTAINER_ID, PartitionKey(path="/id"))

    @staticmethod
    def get_vectorized_container():
        return Settings.get_cosmos_client().create_container_if_not_exists(
            Settings.VECTORIZED_CONTAINER_ID, PartitionKey(path="/id"))

    # cosmos_client = cosmos_client.CosmosClient(
    #     HOST,
    #     {"masterKey": MASTER_KEY},
    #     user_agent="PDFParser",
    #     user_agent_overwrite=True,
    # )
    # db = cosmos_client.create_database_if_not_exists(DATABASE_ID)
    # container = db.create_container_if_not_exists(CONTAINER_ID, PartitionKey(path="/id"))
    # vectorized_container = db.create_container_if_not_exists(VECTORIZED_CONTAINER_ID, PartitionKey(path="/id"))


# Calls OpenAI API to summarize the text
def summarize_resume(resume_text):
    openai.api_key = Settings.OPENAI_API_KEY

    system_prompt = env.get_template("system_prompt.jinja").render()
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo-1106",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content":system_prompt},
            {"role": "user", "content": resume_text},
        ],
    )
    return json.loads(response.choices[0].message.content)

def upsert_resume(contents, resume_blob_location):
    guid = str(uuid.uuid4())
    add_resume_to_cosmos(contents, resume_blob_location, guid)
    add_vectorized_resume_to_cosmos(contents, guid)

# Creates a new item in the Cosmos DB container
def add_resume_to_cosmos(contents, resume_blob_location, guid):
    contents["id"] = guid
    contents["resume_uri"] = resume_blob_location
    try:
        container = Settings.get_container()
        response = container.create_item(body=contents)
    except Exception as e:
        print("add_resume_to_cosmos: ")
        print(e)

def add_vectorized_resume_to_cosmos(contents, guid):
    try:
        vectorized_contents = embed(contents["text"])
        vectorized_contents["id"] = guid
        response = Settings.vectorized_container.create_item(body=vectorized_contents)
    except Exception as e:
        print(e)

def embed(content) -> List[float]:
    openai.api_key = Settings.OPENAI_API_KEY
    res = openai.embeddings.create(
        input=content, model=Settings.EMBEDDING_MODEL
    )
    doc_embeds = [r.embedding for r in res.data]
    return doc_embeds

# Function to move a blob to a processed container
def move_blob(resumes_blob, destination_container_name):
    # Get the source and destination blob clients
    source_blob = Settings.blob_service_client.get_blob_client(
        "resumes", resumes_blob.name.split("/")[-1]
    )
    destination_blob = Settings.blob_service_client.get_blob_client(
        destination_container_name, resumes_blob.name.split("/")[-1] + str(uuid.uuid4())
    )
    # Copy the blob from the source to the destination
    destination_blob.start_copy_from_url(resumes_blob.uri, requires_sync=True)
    # Delete the source blob
    source_blob.delete_blob()
    return destination_blob.url

def store_resume_text_in_blob(text):
    blob_client = Settings.blob_service_client.get_blob_client("resumetext",
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

    try:
        # Push pdf to blob storage
        blob_client = Settings.blob_service_client.get_blob_client("resumes", filename)
        blob_client.upload_blob(file)
    except Exception as e:
        return error_handler(
            "receive_pdf(): An error occurred while uploading the file to blob storage", 500, e)

    return func.HttpResponse(f"File {filename} has been received and saved.")


@app.blob_trigger(arg_name="myblob", path="resumes", connection="BC_PDF_PARSER_STORAGE")
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


    file_location = move_blob(myblob, "processed")
    store_resume_text_in_blob(resume_text)
    process_pdf(file, file_location)

def process_pdf(file, file_location):

    # Create a file-like object from the file
    f = io.BytesIO(file)

    try:
        # Create a PDF reader using the file-like object
        mydoc = PyPDF2.PdfReader(f)
        # Initialize an empty string to store the text
        resume_text = ""
    except Exception as e:
        return error_handler("An error occurred while reading the PDF", 500, e)






    if mydoc.pages is None:
        return error_handler("pdf_loader(): No pages found in the PDF.", 400)

    # Loop through each page in the PDF
    for page in mydoc.pages:
        # Extract the text from the page
        resume_text += page.extract_text()

    summary_text = summarize_resume(resume_text)


    upsert_resume(summary_text, file_location)


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
        response = summarize_resume(text)
    except Exception as e:
        return error_handler("An error occurred while summarizing the text using GPT", 500, e)

    return func.HttpResponse(f"{response}")



@app.route(route="query_resume", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def query_resume(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Query resume function processed a request.')

    search = req.params.get('search')

    if search:
        openai.api_key = Settings.OPENAI_API_KEY
        pinecone = Pinecone(api_key=Settings.PINECONE_API_KEY)
        res = openai.embeddings.create(
            input=search, model=Settings.EMBEDDING_MODEL
        )
        doc_embeds = [r.embedding for r in res.data]

        index = pinecone.Index(Settings.EMBEDDING_MODEL)
        result = index.query(include_metadata=True, vector=doc_embeds[0], top_k=5)
        return func.HttpResponse(f"{result}")
    else:
        return func.HttpResponse(
             "This HTTP triggered function executed successfully. Pass a search in the query string or in the request.",
             status_code=200
        )

