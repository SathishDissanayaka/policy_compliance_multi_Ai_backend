"""Document text extraction with optional OCR fallback.

This module still prefers PyPDF2's native text extraction for speed, but when a
page yields no text (typical for scanned PDFs) we fall back to a HuggingFace
TrOCR model. The heavy OCR components are loaded lazily and cached so only the
first OCR run incurs the model download/initialisation cost. The same OCR path
is reused for standalone image files so the analyzer can handle JPEG/PNG
uploads without additional tooling.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple

import PyPDF2
from PyPDF2.errors import PdfReadError

# Optional imports – they are only required when OCR is enabled. We guard them
# so the rest of the system can operate even if OCR dependencies are missing.
try:  # pragma: no cover - import guard
    import torch
    from pdf2image import convert_from_path
    from PIL import Image
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel
except ImportError:  # pragma: no cover - handled at runtime
    torch = None
    convert_from_path = None
    Image = None
    TrOCRProcessor = None
    VisionEncoderDecoderModel = None


DEFAULT_TROCR_MODEL = os.getenv("TROCR_MODEL_NAME", "microsoft/trocr-base-printed")
POPPLER_PATH = os.getenv("POPPLER_PATH")
ENABLE_OCR = os.getenv("ENABLE_TROCR", "true").lower() in {"1", "true", "yes"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


@lru_cache(maxsize=1)
def _load_ocr_model() -> Optional[Tuple[Any, Any, str]]:
    """Load and cache the TrOCR processor/model (GPU if available).

    Returns ``None`` when OCR is disabled or required deps are missing.
    """

    if not ENABLE_OCR:
        return None
    if any(dep is None for dep in (TrOCRProcessor, VisionEncoderDecoderModel, convert_from_path)):
        # Dependencies are not available – skip OCR.
        print("[OCR] HuggingFace OCR dependencies missing; falling back to PyPDF2 only")
        return None

    print(f"[OCR] Loading TrOCR model '{DEFAULT_TROCR_MODEL}'...")
    processor = TrOCRProcessor.from_pretrained(DEFAULT_TROCR_MODEL)
    model = VisionEncoderDecoderModel.from_pretrained(DEFAULT_TROCR_MODEL)

    device = "cuda" if torch and torch.cuda.is_available() else "cpu"
    if torch:
        model.to(device)

    print(f"[OCR] TrOCR model loaded on device: {device}")
    return processor, model, device


def _run_ocr_on_image(image: Any, processor: Any, model: Any, device: str) -> str:
    """Perform OCR on a single PIL image using the cached TrOCR components."""

    inputs = processor(images=image, return_tensors="pt")
    if torch:
        inputs = {k: v.to(device) for k, v in inputs.items()}

    generated_ids = model.generate(**inputs)
    text = processor.batch_decode(generated_ids, skip_special_tokens=True)
    return text[0] if text else ""


def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from PDFs and common image formats with OCR fallback."""

    _, extension = os.path.splitext(file_path)
    if extension.lower() in IMAGE_EXTENSIONS:
        return _extract_text_from_image(file_path)

    return _extract_text_from_pdf(file_path)


def _extract_text_from_pdf(file_path: str) -> str:
    """Extract text from a PDF, invoking OCR on image-only pages when needed."""

    page_texts: Dict[int, str] = {}
    pages_requiring_ocr = []

    with open(file_path, "rb") as file_pointer:
        try:
            reader = PyPDF2.PdfReader(file_pointer)
        except (PdfReadError, Exception) as exc:
            print(f"[OCR] Unable to parse as PDF, attempting image OCR: {exc}")
            return _extract_text_from_image(file_path)
        for index, page in enumerate(reader.pages, start=1):
            extracted = page.extract_text() or ""
            if extracted.strip():
                page_texts[index] = extracted
            else:
                pages_requiring_ocr.append(index)

    if pages_requiring_ocr:
        ocr_components = _load_ocr_model()
        if ocr_components:
            processor, model, device = ocr_components
            try:
                images = convert_from_path(
                    file_path,
                    dpi=300,
                    poppler_path=POPPLER_PATH or None,
                )
                for index in pages_requiring_ocr:
                    try:
                        image = images[index - 1]
                    except IndexError:
                        continue  # Defensive: skip if rendering failed for the page
                    # Ensure a consistent channel layout for the transformer
                    safe_image = image.convert("RGB") if hasattr(image, "convert") else image
                    ocr_text = _run_ocr_on_image(safe_image, processor, model, device)
                    if ocr_text.strip():
                        page_texts[index] = ocr_text
            except Exception as exc:  # pragma: no cover - runtime safeguard
                print(f"[OCR] Failed to run OCR fallback: {exc}")
        else:
            print("[OCR] OCR components unavailable; some pages may remain blank")

    if not page_texts:
        return ""

    ordered_pages = [page_texts[idx] for idx in sorted(page_texts.keys())]
    return "\n\n".join(ordered_pages)


def _extract_text_from_image(file_path: str) -> str:
    """Run OCR directly on an image file."""

    ocr_components = _load_ocr_model()
    if not ocr_components or Image is None:
        print("[OCR] OCR components unavailable for image input;")
        return ""

    processor, model, device = ocr_components
    try:
        with Image.open(file_path) as image:
            # Convert animated images (e.g. GIF/TIFF) frame-by-frame.
            if getattr(image, "is_animated", False):
                texts = []
                for frame in range(image.n_frames):
                    image.seek(frame)
                    texts.append(_run_ocr_on_image(image.convert("RGB"), processor, model, device))
                return "\n\n".join(texts).strip()

            return _run_ocr_on_image(image.convert("RGB"), processor, model, device).strip()
    except Exception as exc:
        print(f"[OCR] Failed to process image: {exc}")
        return ""
