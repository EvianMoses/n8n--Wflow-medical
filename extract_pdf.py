import sys
import json
import base64
import fitz  # PyMuPDF

# Maximum number of images to extract from the PDF.
MAX_IMAGES = 3


def extract_pdf(pdf_path):
    doc = fitz.open(pdf_path)

    extracted_text = ""
    images = []

    for page in doc:
        # Text extraction.
        extracted_text += page.get_text()

        # Image extraction (Base64, no disk writes), capped at MAX_IMAGES.
        if len(images) < MAX_IMAGES:
            for img in page.get_images(full=True):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]  # e.g. "png", "jpeg"

                images.append({
                    "mime_type": f"image/{image_ext}",
                    "data": base64.b64encode(image_bytes).decode("utf-8"),
                })

                if len(images) >= MAX_IMAGES:
                    break

    doc.close()

    return {
        "text": extracted_text.strip(),
        "images": images,
    }


if __name__ == "__main__":
    result = extract_pdf(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False))
