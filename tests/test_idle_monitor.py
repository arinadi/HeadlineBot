"""In GEMINI (CPU) mode idle timers run 5x longer, so the runtime isn't killed
while users are still uploading."""
import asyncio
import time

from headlinebot.bot_classes import IdleMonitor
from headlinebot.config import Config
from tests.fakes import FakeApp


class IdleJobs:
    def is_idle(self):
        return True


def test_multiplier_stretches_time_until_shutdown():
    monitor = IdleMonitor(FakeApp(), IdleJobs(), shutdown_callback=None, timeout_multiplier=5)
    before = time.time()
    asyncio.run(monitor.check_idle())
    expected = Config.IDLE_SHUTDOWN_MINUTES * 5 * 60
    assert abs((monitor.shutdown_on - before) - expected) < 5


def test_multiplier_delays_first_alert():
    app = FakeApp()
    monitor = IdleMonitor(app, IdleJobs(), shutdown_callback=None, timeout_multiplier=5)
    # Idle for just past the un-multiplied first-alert time.
    elapsed_minutes = Config.IDLE_FIRST_ALERT_MINUTES + 0.5
    monitor.shutdown_on = time.time() + (Config.IDLE_SHUTDOWN_MINUTES * 5 - elapsed_minutes) * 60
    asyncio.run(monitor.check_idle())
    assert app.bot.sent == []
