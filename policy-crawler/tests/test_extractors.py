import unittest

from extractors import OCRExtractor, PDFExtractor


class TestExtractors(unittest.TestCase):
    def test_pdf_injected_engine(self):
        ex = PDFExtractor(engine=lambda src: "PDF提取正文")
        self.assertEqual(ex.extract(b"fake"), "PDF提取正文")

    def test_pdf_default_returns_empty_on_invalid_input(self):
        ex = PDFExtractor()
        self.assertEqual(ex.extract(b"not a pdf"), "")

    def test_ocr_injected_engine(self):
        ex = OCRExtractor(engine=lambda src: "OCR识别文本")
        self.assertEqual(ex.extract(b"fake"), "OCR识别文本")

    def test_ocr_default_defensive(self):
        ex = OCRExtractor()
        self.assertEqual(ex.extract(b"fake"), "")


if __name__ == "__main__":
    unittest.main()
