import azure.functions as func
import azure.storage.blob as blob
import os
import tempfile
import logging

# Get connection string from environment
connection_string = os.environ["AzureWebJobsStorage"]

# Create a BlobServiceClient
blob_service_client = blob.BlobServiceClient.from_connection_string(connection_string)

app = func.FunctionApp()

# Function decorator 
@app.function_name('receivePDF')
@app.route(route='/api/receivePDF', methods=['POST'], auth_level=func.AuthLevel.ANONYMOUS)
def receive_pdf(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    file = req.files.get('pdf')

    if not file:
        return func.HttpResponse(
             "No file found in the request",
             status_code=400
        )

    # Push pdf to blob storage
    blob_client = blob_service_client.get_blob_client("resumes", file.filename)
    blob_client.upload_blob(file)

    return func.HttpResponse(f"File {file.filename} has been received and saved.")
