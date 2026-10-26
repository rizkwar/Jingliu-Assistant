from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtGui import QColor, QImage

from companion.chat import attachments
from companion.chat.llm import openrouter_message
from companion.core.storage import Store
from tests.qt_test_support import application


class AttachmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        application()

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.store_root = self.root / "attachments"

    def image(self, name, width, height):
        image = QImage(width, height, QImage.Format.Format_RGB32)
        image.fill(QColor("#a8d4ff"))
        image.save(str(self.root / name))
        return self.root / name

    def test_classify_accepts_images_pdfs_and_text_but_not_binaries(self):
        (self.root / "notes.md").write_text("# Plan\n- tea", encoding="utf-8")
        (self.root / "doc.pdf").write_bytes(b"%PDF-1.4")
        (self.root / "app.exe").write_bytes(b"MZ\0\0binary")
        (self.root / "fake.png").write_bytes(b"not an image")
        self.assertEqual(attachments.classify(self.image("a.png", 4, 4)), ("image", "image/png"))
        self.assertEqual(attachments.classify(self.root / "notes.md"), ("text", "text/plain"))
        self.assertEqual(attachments.classify(self.root / "doc.pdf"), ("pdf", "application/pdf"))
        for name in ("app.exe", "fake.png", "missing.txt"):
            with self.subTest(name), self.assertRaises(attachments.AttachmentError):
                attachments.classify(self.root / name)

    def test_store_copies_and_downscales_large_images(self):
        large = self.image("large.png", 4000, 2000)
        (self.root / "log.txt").write_text("x" * 10, encoding="utf-8")
        stored = attachments.store([large, self.root / "log.txt"], self.store_root)
        image = QImage(stored[0]["path"])
        self.assertEqual(max(image.width(), image.height()), attachments.MAX_IMAGE_EDGE)
        self.assertEqual(stored[0]["mime"], "image/jpeg")
        self.assertEqual(stored[1]["kind"], "text")
        self.assertTrue(Path(stored[1]["path"]).is_relative_to(self.store_root))
        self.assertTrue(large.exists())  # The original is never moved or changed.
        with self.assertRaises(attachments.AttachmentError):
            attachments.store([large] * (attachments.MAX_FILES + 1), self.store_root)

    def test_long_text_is_truncated_with_a_marker(self):
        path = self.root / "big.log"
        path.write_text("y" * (attachments.MAX_TEXT_CHARS + 50), encoding="utf-8")
        text = attachments.read_text({"name": "big.log", "path": str(path)})
        self.assertIn("truncated", text)
        self.assertLess(len(text), attachments.MAX_TEXT_CHARS + 200)

    def test_openrouter_parts_use_data_urls(self):
        stored = attachments.store([self.image("a.png", 8, 8)], self.store_root)
        message = openrouter_message({"role": "user", "content": "What is this?", "attachments": stored})
        self.assertEqual(message["content"][0], {"type": "text", "text": "What is this?"})
        self.assertTrue(message["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(openrouter_message({"role": "user", "content": "Hi"}), {"role": "user", "content": "Hi"})

    def test_history_keeps_a_note_and_deleting_the_chat_removes_copies(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        stored = attachments.store([self.image("cat.png", 8, 8)], self.store_root)
        conversation = store.create_conversation()
        turn = store.start_turn(conversation, "", stored)
        store.save_turn(turn, "A small blue square.", "A small blue square.", "complete")
        self.assertEqual(store.conversation(conversation)["title"], "cat.png")
        self.assertEqual(store.context(conversation)[0]["content"], "[Attached image: cat.png]")
        self.assertEqual(attachments.loads(store.messages(conversation)[0]["attachments"])[0]["name"], "cat.png")
        with patch("companion.chat.attachments.ATTACHMENT_ROOT", self.store_root):
            store.delete_conversation(conversation)
        self.assertFalse(Path(stored[0]["path"]).exists())
        outside = self.root / "keep.txt"
        outside.write_text("keep", encoding="utf-8")
        attachments.remove_files([{"name": "keep.txt", "kind": "text", "path": str(outside)}], self.store_root)
        self.assertTrue(outside.exists())  # Paths outside the attachment folder are never deleted.
