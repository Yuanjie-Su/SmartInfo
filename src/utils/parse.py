import re
from typing import List, Dict

def parse_markdown_analysis_output(markdown_text: str) -> List[Dict[str, str]]:
    """
    Extract title, link, date, summary, and analysis fields from the markdown analysis text output by the large model.
    Return a structured list.
    """
    articles = []
    # Split the text into blocks using the '---' separator
    blocks = markdown_text.strip().split('\n---\n')

    for block in blocks:
        # Skip the final concluding paragraph if it doesn't start like an article block
        if not block.strip().startswith("###"):
            continue

        article_data = {}
        lines = block.strip().split('\n')
        
        # Filter out empty lines potentially caused by multiple newlines
        lines = [line.strip() for line in lines if line.strip()]

        summary_lines = []
        analysis_lines = []
        in_summary = False
        in_analysis = False

        for line in lines:
            if line.startswith("### "):
                article_data['title'] = line[len("### "):].strip()
                in_summary = False
                in_analysis = False
            elif line.startswith("🔗 "):
                article_data['link'] = line[len("🔗 "):].strip()
                in_summary = False
                in_analysis = False
            elif line.startswith("📅 "):
                article_data['date'] = line[len("📅 "):].strip()
                in_summary = False
                in_analysis = False
            elif line.startswith("**Summary:**"):
                summary_lines.append(line[len("**Summary:**"):].strip())
                in_summary = True
                in_analysis = False
            elif line.startswith("**Analysis:**"):
                analysis_lines.append(line[len("**Analysis:**"):].strip())
                in_analysis = True
                in_summary = False
            elif in_summary:
                # Handle multi-line summaries if they occur
                summary_lines.append(line)
            elif in_analysis:
                # Handle multi-line analyses if they occur
                analysis_lines.append(line)

        # Join the lines for summary and analysis
        article_data['summary'] = " ".join(summary_lines)
        article_data['analysis'] = " ".join(analysis_lines)

        # Add the extracted data to the list if all keys are present
        if all(key in article_data for key in ['title', 'link', 'date', 'summary', 'analysis']):
            articles.append(article_data)
            
    return articles 

if __name__ == "__main__":
    try:
        # Assuming analysis_result.txt contains the text you want to parse [cite: 1]
        with open("analysis_result.txt", "r", encoding="utf-8") as file:
            markdown_text = file.read()
        parsed_result = parse_markdown_analysis_output(markdown_text)
        # Now this will print the list of dictionaries, not None
        print(parsed_result) 
    except FileNotFoundError:
        print("Error: analysis_result.txt not found.")
    except Exception as e:
        print(f"An error occurred: {e}")