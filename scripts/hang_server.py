#!/usr/bin/env python3
"""
Minimal "black hole" HTTP-ish server: accepts a TCP connection and then
never writes a response and never closes it. Used to simulate a truly
hung outbound dependency (worse than a slow-but-eventually-responding
endpoint) for the BUG #2/#3 demo -- proves a request with no timeout
blocks forever, not just "a while".

Usage: python3 scripts/hang_server.py <port>
"""
import socket
import sys
import threading


def handle(conn):
    with conn:
        try:
            conn.recv(65536)  # read the request, then just... never respond
        except Exception:
            pass
        while True:
            threading.Event().wait(3600)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 19191
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(50)
    print(f"hang_server listening on :{port} -- accepts connections, never responds", flush=True)
    while True:
        conn, addr = srv.accept()
        print(f"accepted connection from {addr}, will hang forever", flush=True)
        threading.Thread(target=handle, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    main()
