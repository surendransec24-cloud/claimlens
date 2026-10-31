import os
from typing import Dict, Any, List
import pdfplumber

class PDFService:
    @staticmethod
    def extract_text_and_tables(file_path: str) -> Dict[str, Any]:
        """Extracts text, page count, and tabular data from a PDF file using pdfplumber."""
        result: Dict[str, Any] = {
            "page_count": 0,
            "full_text": "",
            "pages": [],
            "tables": []
        }
        
        if not os.path.exists(file_path):
            return result
            
        try:
            with pdfplumber.open(file_path) as pdf:
                result["page_count"] = len(pdf.pages)
                all_text = []
                for i, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    all_text.append(f"--- PAGE {i+1} ---\n{text}")
                    result["pages"].append({
                        "page_number": i + 1,
                        "text": text
                    })
                    tables = page.extract_tables()
                    if tables:
                        for tbl in tables:
                            result["tables"].append({
                                "page_number": i + 1,
                                "data": tbl
                            })
                result["full_text"] = "\n\n".join(all_text)
        except Exception as e:
            result["error"] = str(e)
            
        return result

