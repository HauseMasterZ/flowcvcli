"""Cover letters: listing, create/duplicate id handling, body/title/delete/download shapes."""
import json
import unittest

from flowcvcli.api import FlowCV
from flowcvcli.config import Config
from flowcvcli.letters import letter_text_to_html

SRC = {"id": "SRC", "uuid": "U", "title": "Mine", "mongoId": "m",
       "createdAt": "c", "updatedAt": "u", "lastChangeAt": "l",
       "content": {"body": "<p>Hi.</p>"}, "design": {}}


class FakeFlowCV(FlowCV):
    """Scripted letter endpoints; records every call."""

    def __init__(self, env=None):
        super().__init__(config=Config(cookie="flowcvsidapp=x"))
        self._env = env or {"success": True, "data": {}}
        self.calls = []

    def request(self, path, method="GET", body=None, query=None, timeout=30):
        self.calls.append({"path": path, "method": method, "body": body, "query": query})
        if path == "letters/all":
            return {"success": True, "data": {"letters": [json.loads(json.dumps(SRC))]}}
        if path == "letters/SRC":
            return {"success": True, "data": {"letter": json.loads(json.dumps(SRC))}}
        return self._env


class LettersTest(unittest.TestCase):
    def test_list_letters(self):
        fc = FakeFlowCV()
        letters = fc.list_letters()
        self.assertEqual([L["id"] for L in letters], ["SRC"])
        self.assertEqual(fc.calls[-1]["path"], "letters/all")

    def test_get_letter(self):
        fc = FakeFlowCV()
        self.assertEqual(fc.get_letter("SRC")["title"], "Mine")

    def test_create_returns_server_id_and_drops_mongo_fields(self):
        fc = FakeFlowCV({"success": True, "data": {"letter": {"id": "SERVER-ID"}}})
        self.assertEqual(fc.create_letter("New", src=json.loads(json.dumps(SRC))), "SERVER-ID")
        sent = fc.calls[-1]["body"]["clientLetter"]
        self.assertEqual(sent["title"], "New")
        self.assertNotEqual(sent["id"], "SRC")
        for k in ("mongoId", "createdAt", "updatedAt", "lastChangeAt"):
            self.assertNotIn(k, sent)

    def test_save_body_posts_html(self):
        fc = FakeFlowCV()
        fc.save_letter_body("SRC", "<p>Hi.</p>")
        call = fc.calls[-1]
        self.assertEqual((call["path"], call["method"]), ("letters/save_body", "POST"))
        self.assertEqual(call["body"], {"letterId": "SRC", "body": "<p>Hi.</p>"})

    def test_save_title_posts_shape(self):
        fc = FakeFlowCV()
        fc.save_letter_title("SRC", "New Title")
        call = fc.calls[-1]
        self.assertEqual((call["path"], call["method"]), ("letters/save_title", "POST"))
        self.assertEqual(call["body"], {"letterId": "SRC", "title": "New Title"})

    def test_delete_uses_query(self):
        fc = FakeFlowCV()
        fc.delete_letter("SRC")
        call = fc.calls[-1]
        self.assertEqual((call["path"], call["method"]), ("letters/delete_letter", "DELETE"))
        self.assertEqual(call["query"], {"letterId": "SRC"})

    def test_text_to_html_paragraphs(self):
        self.assertEqual(letter_text_to_html("Hi,\n\nSecond <line>."),
                         "<p>Hi,</p><p>Second &lt;line&gt;.</p>")


if __name__ == "__main__":
    unittest.main()
