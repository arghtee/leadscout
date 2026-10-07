"""RQ worker entry point. Pipeline jobs arrive in later milestones."""

from redis import Redis
from rq import Queue, Worker

from leadscout.config import get_settings

QUEUE_NAMES = ("default",)


def heartbeat() -> str:
    return "ok"


def main() -> None:
    conn = Redis.from_url(get_settings().redis_url)
    queues = [Queue(name, connection=conn) for name in QUEUE_NAMES]
    Worker(queues, connection=conn).work()


if __name__ == "__main__":
    main()
