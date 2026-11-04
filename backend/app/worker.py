import signal
import threading
from app.db.migrate import migrate
from app.services.jobs import worker_loop

if __name__ == '__main__':
    migrate()
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    worker_loop(stop)
