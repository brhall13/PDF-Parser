import PyPDF2

def pdf_to_text(file_path):
    # Open the PDF file in binary mode
    with open(file_path, 'rb') as file:
        # Create a PDF file reader object
        pdf_reader = PyPDF2.PdfReader(file)
        
        # Initialize an empty string to store the text
        text = ''
        
        # Loop through each page in the PDF
        for page in pdf_reader.pages:
            # Extract the text from the page
            text += page.extract_text()
        
    return text

# Change variable to a command argument later
file_path = 'functionalsample.pdf'
text = pdf_to_text(file_path)
print(text)

if __name__ == '__main__':
    print(pdf_to_text(file_path))