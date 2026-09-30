import asyncio

from headlinebot.bot_classes import Job, JobManager
from tests.fakes import FakeApp


class FakeIdleMonitor:
    def reset(self):
        pass


def make_manager():
    ready = asyncio.Event()
    ready.set()
    return JobManager(FakeApp(), FakeIdleMonitor(), ready)


def make_job(name="rapat.m4a"):
    return Job(message_id=1, chat_id=1, original_filename=name, local_filepath=name, job_type="transcript")


def test_queued_job_can_be_cancelled():
    async def scenario():
        manager, job = make_manager(), make_job()
        await manager.add_job(job)
        return await manager.cancel_job(job.job_id), manager.get_queued_jobs()

    (cancelled, name), queued = asyncio.run(scenario())
    assert cancelled and name == "rapat.m4a"
    assert queued == []


def test_job_being_processed_cannot_be_cancelled():
    async def scenario():
        manager, job = make_manager(), make_job()
        await manager.add_job(job)
        manager.set_processing_job(job)
        return await manager.cancel_job(job.job_id), job.status

    (cancelled, _), status = asyncio.run(scenario())
    assert not cancelled
    assert status == "processing"
