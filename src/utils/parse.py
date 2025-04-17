import re
from typing import List, Dict


def parse_markdown_analysis_output(markdown_text: str) -> List[Dict[str, str]]:
    """
    Extract title, link, date, and summary fields from the markdown analysis text output by the large model.
    Return a structured list.
    """
    articles = []
    # Split the text into blocks using the '---' separator
    blocks = markdown_text.strip().split("\n---\n")

    for block in blocks:
        # Skip blocks that don't start with an article title
        if not block.strip().startswith("###"):
            continue

        article_data = {}
        # Remove empty lines and split into lines
        lines = [line.strip() for line in block.strip().split("\n") if line.strip()]

        summary_lines = []
        in_summary = False

        for line in lines:
            if line.startswith("### "):
                article_data["title"] = line[len("### ") :].strip()
                in_summary = False
            elif line.startswith("🔗 "):
                article_data["link"] = line[len("🔗 ") :].strip()
                in_summary = False
            elif line.startswith("📅 "):
                article_data["date"] = line[len("📅 ") :].strip()
                in_summary = False
            elif line.startswith("**Summary:**"):
                summary_lines.append(line[len("**Summary:**") :].strip())
                in_summary = True
            elif in_summary:
                # Handle multi-line summaries if they occur
                summary_lines.append(line)

        article_data["summary"] = " ".join(summary_lines)

        # Only add to results if all keys are present
        if all(key in article_data for key in ["title", "link", "date", "summary"]):
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
