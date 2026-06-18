"""PDF text extraction utilities."""
import fitz  # pymupdf


def extract_text_from_pdf(file_path: str) -> str:
    """Extract all text from a PDF file.

    Args:
        file_path: Path to the PDF file.

    Returns:
        Extracted text content.

    Raises:
        ValueError: If the PDF is empty or cannot be read.
    """
    try:
        doc = fitz.open(file_path)
        text_parts = []
        for page in doc:
            text = page.get_text()
            if text.strip():
                text_parts.append(text.strip())

        doc.close()

        full_text = "\n\n".join(text_parts)
        if not full_text.strip():
            raise ValueError("PDF contains no extractable text (possibly scanned PDF)")

        return full_text
    except Exception as e:
        raise ValueError(f"Failed to extract text from PDF: {e}")
