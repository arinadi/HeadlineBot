"""The VPS launcher wakes a Colab VM when the chat needs the bot.

While no VM runs it long-polls Telegram. The first message from the bot's chat
starts Colab and is left unconfirmed, so the bot on Colab receives it. While a
VM runs (or its state is unknown) the launcher never polls: Telegram allows one
getUpdates consumer per bot, and it must be the bot.
"""
import launcher

CHAT = 42


def message(update_id, chat_id=CHAT):
    return {"update_id": update_id, "message": {"message_id": 1, "chat": {"id": chat_id}, "text": "hi"}}


def button(update_id, chat_id=CHAT):
    return {"update_id": update_id, "callback_query": {"id": "q", "message": {"chat": {"id": chat_id}}}}


class FakeTelegram:
    def __init__(self, *batches):
        self.batches = list(batches)
        self.offsets = []
        self.sent = []

    def get_updates(self, offset):
        self.offsets.append(offset)
        return self.batches.pop(0) if self.batches else []

    def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))


class FakeColab:
    def __init__(self, states, start_ok=True, start_detail=""):
        self.states = list(states)
        self.start_ok, self.start_detail = start_ok, start_detail
        self.calls = []

    def session_state(self):
        return self.states.pop(0)

    def start(self):
        self.calls.append("start")
        return self.start_ok, self.start_detail


def make(telegram, colab):
    calls = colab.calls
    return launcher.Launcher(telegram, colab, chat_id=CHAT, pull_code=lambda: calls.append("pull"))


def test_never_polls_telegram_while_a_vm_runs():
    telegram = FakeTelegram([message(10)])
    assert make(telegram, FakeColab([True])).step() == "busy"
    assert telegram.offsets == []


def test_unknown_vm_state_counts_as_busy():
    telegram = FakeTelegram([message(10)])
    assert make(telegram, FakeColab([None])).step() == "busy"
    assert telegram.offsets == []


def test_message_from_the_chat_wakes_colab_and_stays_unconfirmed():
    telegram = FakeTelegram([message(10)], [])
    colab = FakeColab([False, False])
    bot_launcher = make(telegram, colab)
    assert bot_launcher.step() == "woke"
    assert colab.calls == ["pull", "start"]
    assert telegram.sent and telegram.sent[0][0] == CHAT
    bot_launcher.step()
    # Next poll must not confirm update 10 (offset > 10 would drop it for the bot).
    assert telegram.offsets[-1] <= 10


def test_other_chats_and_button_presses_are_confirmed_and_ignored():
    telegram = FakeTelegram([message(5, chat_id=999), button(6)], [])
    colab = FakeColab([False, False])
    bot_launcher = make(telegram, colab)
    assert bot_launcher.step() == "idle"
    assert colab.calls == []
    bot_launcher.step()
    assert telegram.offsets[-1] == 7


def test_failed_start_tells_the_chat_and_skips_the_message():
    telegram = FakeTelegram([message(10)], [])
    colab = FakeColab([False, False], start_ok=False, start_detail="GPU T4 not available")
    bot_launcher = make(telegram, colab)
    assert bot_launcher.step() == "failed"
    assert any("GPU T4 not available" in text for _, text in telegram.sent)
    bot_launcher.step()
    assert telegram.offsets[-1] == 11


def test_listens_again_once_the_vm_is_gone():
    telegram = FakeTelegram([])
    bot_launcher = make(telegram, FakeColab([True, False]))
    assert bot_launcher.step() == "busy"
    assert bot_launcher.step() == "idle"
    assert len(telegram.offsets) == 1


def test_session_state_from_colab_sessions_output():
    line = "[headlinebot] https://x.colab.dev | Hardware: T4 | Shape: STANDARD | Variant: GPU"
    assert launcher.session_state_from(line, "headlinebot") is True
    assert launcher.session_state_from("[colab] No active sessions found on server.", "headlinebot") is False
    assert launcher.session_state_from("[other] https://y | Hardware: CPU", "headlinebot") is False
    assert launcher.session_state_from("Traceback (most recent call last): ...", "headlinebot") is None
