import argparse
from openai import OpenAI
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

def generate_resume(position):
    openai = OpenAI()

    prompt = f"Generate a resume for a {position}"

    response = openai.chat.completions.create(
        model="gpt-3.5-turbo-1106",
        messages=[
            {"role": "system",
              "content": "You are an AI assistant that creates sample resumes for testing purposes. Create fictional information such as, 'John Smith', '505 ABC Road', 'Good University', 'Best Business', etc. Fill in all fields, do not use 'City', 'Full Name', etc. Do not use real personal information."},
            {"role": "user", "content": prompt},
        ],
    )

    text = response.choices[0].message.content
    
    # testing
    # print(text)

    return text



def convert_to_pdf(text, output_filename):
    # Save the resume text to a file
    with open('resume.txt', 'w') as file:
        file.write(text)
    
    # Convert the resume to PDF
    os.system(f'cupsfilter resume.txt > {output_filename}')
    

def main():
    """
    Generate a resume and save as PDF.

    Args:
        position (str): The position for the resume
        output (str, optional): The output PDF file. Defaults to 'resume.pdf'.
    """
    parser = argparse.ArgumentParser(description='Generate a resume and save as PDF.')
    parser.add_argument('position', type=str, help='The position for the resume')
    parser.add_argument('-o', '--output', type=str, default='resume.pdf', help='The output PDF file')

    args = parser.parse_args()

    resume_text = generate_resume(args.position)
    convert_to_pdf(resume_text, args.output)


if __name__ == '__main__':
    main()