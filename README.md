# PDF-Parser

## Description
This project is a Python application that downloads and parses PDF files from an Azure Blob Storage container.

## Installation
1. Clone this repository.
2. Install the required Python packages: `pip install -r requirements.txt`
3. Set up your Azure Blob Storage and get the connection string.
4. Create a `.env` file in the root directory of the project and add your Azure Blob Storage connection string as `CONNECTION_STRING`.

## Usage
1. Run the script: `python PDF-Parser.py`
2. The script will download all PDF files from the specified Azure Blob Storage container to the `PDFS` directory.
3. The script will then parse the downloaded PDF files (this functionality needs to be implemented).

## License
[MIT](https://choosealicense.com/licenses/mit/)