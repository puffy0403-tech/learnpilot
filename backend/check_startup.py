"""Preflight for the Windows launcher; do not terminate other processes."""
import socket
from pathlib import Path
from dotenv import load_dotenv


def port_available(port):
    with socket.socket() as probe:
        try:
            probe.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False


def main():
    busy = [p for p in (8000, 5173) if not port_available(p)]
    if busy:
        print('Ports already in use: ' + ', '.join(map(str, busy)))
        print('Close the existing LearnPilot backend/frontend windows with Ctrl+C, then retry.')
        print('No new services were started. Do not run multiple project copies at once.')
        return 1
    load_dotenv(Path(__file__).parent / '.env')
    from database import DB_PATH
    print('Database: ' + str(DB_PATH.resolve()))
    if not DB_PATH.exists():
        print('No existing database here. For old accounts, close services and run the data restore tool.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
