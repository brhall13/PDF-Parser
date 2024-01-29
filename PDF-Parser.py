import PyPDF2

def pdf_to_text(file_path):
    # Open the PDF file in binary mode
    with open(file_path, 'rb') as file:
        # Create a PDF file reader object
        pdf_reader = PyPDF2.PdfFileReader(file)
        
        # Initialize an empty string to store the text
        text = ''
        
        # Loop through each page in the PDF
        for page_num in range(pdf_reader.numPages):
            # Extract the text from the page
            page = pdf_reader.getPage(page_num)
            text += page.extractText()
        
    return text

# Change variable to a command argument later
file_path = 'path_to_your_pdf_file.pdf'
text = pdf_to_text(file_path)
print(text)