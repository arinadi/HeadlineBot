"""Stand-ins for services we don't own (Gemini client, Telegram bot)."""
from types import SimpleNamespace


class FakeGeminiModels:
    def __init__(self, replies):
        # Each reply is a str (returned as .text) or an Exception (raised).
        self._replies = list(replies)
        self.calls = []

    def generate_content(self, model, contents, config=None):
        self.calls.append(SimpleNamespace(model=model, contents=contents))
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(text=reply, candidates=None)


class FakeGeminiFiles:
    def __init__(self, upload_error=None):
        self.upload_error = upload_error
        self.deleted = []

    def upload(self, file):
        if self.upload_error:
            raise self.upload_error
        return SimpleNamespace(name="files/abc123", state=SimpleNamespace(name="PROCESSING"))

    def get(self, name):
        return SimpleNamespace(name=name, state=SimpleNamespace(name="ACTIVE"))

    def delete(self, name):
        self.deleted.append(name)


class FakeGeminiClient:
    def __init__(self, replies=(), upload_error=None):
        self.models = FakeGeminiModels(replies)
        self.files = FakeGeminiFiles(upload_error)


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeApp:
    def __init__(self):
        self.bot = FakeBot()
