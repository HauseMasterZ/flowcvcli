"""Cover-letter operations: listing, create/duplicate, body/title edits,
delete, PDF download.

Letters live beside resumes under the same session: `letters/all` lists
them, `letters/<id>` fetches one, and mutations go to dedicated endpoints
(create/duplicate as POST, save_body/save_title as POST, delete_letter as
DELETE, download as GET). Endpoint shapes were verified live against the
real API; `duplicate_letter`'s payload mirrors the site's own duplicate
call. Like resumes, create mints the id server-side — always read it back.
"""
import datetime
import json
import os
import uuid

from .config import backups_dir
from .errors import ApiError

# Top-level letter fields the server regenerates on create: drop them from
# clones so a copy never collides with (or shadows) the source.
_NEW_LETTER_DROP = ("mongoId", "createdAt", "updatedAt", "lastChangeAt")


def letter_text_to_html(text):
    """Plain paragraphs (blank-line separated) -> <p> HTML. No markup."""
    paras = [p.strip() for p in (text or "").split("\n\n") if p.strip()]

    def esc(s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    return "".join(f"<p>{esc(p).replace(chr(10), '<br/>')}</p>" for p in paras)


class LetterMixin:
    # ---- listing / fetch ------------------------------------------------
    def list_letters(self):
        """GET /letters/all -> the list of letter summaries. Raises on failure."""
        env = self.request("letters/all")
        if not env.get("success"):
            raise ApiError(f"list letters failed: {json.dumps(env)[:200]}")
        return (env.get("data") or {}).get("letters") or []

    def get_letter(self, letter_id):
        """GET /letters/<id> -> the full letter object. Raises on failure."""
        env = self.request(f"letters/{letter_id}")
        if not env.get("success"):
            raise ApiError(f"get letter failed (code {env.get('code')}): "
                           f"{env.get('error') or ''}")
        letter = (env.get("data") or {}).get("letter")
        if not letter:
            raise ApiError(f"get letter {letter_id}: empty response")
        return letter

    # ---- create / duplicate ---------------------------------------------
    def _create_letter_from(self, title, src):
        """POST /letters/create with a cloned letter object. Returns the
        server-minted id (the server ignores the client-supplied one)."""
        clone = json.loads(json.dumps(src))    # deep copy
        clone["id"] = str(uuid.uuid4())
        clone["uuid"] = str(uuid.uuid4())
        clone["title"] = title
        for k in _NEW_LETTER_DROP:
            clone.pop(k, None)
        env = self.request("letters/create", method="POST",
                           body={"clientLetter": clone})
        if not env.get("success"):
            raise ApiError(f"create letter failed: {json.dumps(env)[:200]}")
        created = (env.get("data") or {}).get("letter") or {}
        return created.get("id") or clone["id"]

    def create_letter(self, title, src=None):
        """Create a letter cloning `src` (a letter object, or the first letter
        on the account when omitted). Returns the new letter id."""
        if src is None:
            letters = self.list_letters()
            if not letters:
                raise ApiError("no letters to clone structure from")
            src = self.get_letter(letters[0]["id"])
        return self._create_letter_from(title, src)

    def duplicate_letter(self, letter_id, title=None):
        """Duplicate by re-creating from a fetched copy.

        The native POST /letters/duplicate endpoint exists but rejects every
        tried payload shape (400s across a dozen variants), so duplication is
        implemented as get + create — semantically identical, fully verified.
        Returns the new letter id.
        """
        src = self.get_letter(letter_id)
        if title is None:
            title = (src.get("title") or "Letter") + " (copy)"
        return self._create_letter_from(title, src)

    # ---- edits ------------------------------------------------------------
    def save_letter_body(self, letter_id, html):
        """POST /letters/save_body — replace the letter body (<p> HTML)."""
        env = self.request("letters/save_body", method="POST",
                           body={"letterId": letter_id, "body": html})
        if not env.get("success"):
            raise ApiError(f"save letter body failed: {json.dumps(env)[:200]}")
        return env

    def set_letter_body_text(self, letter_id, text):
        """Plain-text convenience over save_letter_body (paragraphs -> <p>)."""
        return self.save_letter_body(letter_id, letter_text_to_html(text))

    def save_letter_title(self, letter_id, title):
        """POST /letters/save_title — rename the letter."""
        env = self.request("letters/save_title", method="POST",
                           body={"letterId": letter_id, "title": title})
        if not env.get("success"):
            raise ApiError(f"rename letter failed: {json.dumps(env)[:200]}")
        return env

    # ---- backup / delete ----------------------------------------------------
    def backup_letter(self, letter_id):
        """Snapshot a letter to backups/ (dir 0o700, file 0o600). Returns path."""
        blob = json.dumps(self.get_letter(letter_id), indent=2, ensure_ascii=False)
        d = backups_dir()
        os.makedirs(d, mode=0o700, exist_ok=True)
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = os.path.join(d, f"letter-{letter_id}-{ts}.json")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(blob)
        return path

    def delete_letter(self, letter_id):
        """DELETE /letters/delete_letter — permanent. Back up first."""
        env = self.request("letters/delete_letter", method="DELETE",
                           query={"letterId": letter_id})
        if not env.get("success"):
            raise ApiError(f"delete letter failed: {json.dumps(env)[:200]}")
        return env

    # ---- PDF ------------------------------------------------------------------
    def download_letter_pdf(self, letter_id):
        """GET /letters/download -> PDF bytes. Raises unless 200 + %PDF."""
        status, raw = self.request_raw(
            "letters/download", query={"letterId": letter_id})
        if status != 200 or not raw.startswith(b"%PDF"):
            raise ApiError(f"letter download failed: HTTP {status}, {raw[:80]!r}")
        return raw

    def save_letter_pdf(self, letter_id, path):
        """Download the letter PDF and write it to `path`; return `path`."""
        with open(path, "wb") as f:
            f.write(self.download_letter_pdf(letter_id))
        return path
