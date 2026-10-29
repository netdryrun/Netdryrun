"""Relay Ollama (127.0.0.1:11434 on Windows) to the WSL vEthernet address so agents in Ubuntu-ndr can reach it."""
import socket, sys, threading

LISTEN, TARGET = (sys.argv[1], int(sys.argv[2])), ("127.0.0.1", 11434)


def pipe(a, b):
    try:
        while (d := a.recv(65536)):
            b.sendall(d)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(LISTEN)
srv.listen(64)
while True:
    c, _ = srv.accept()
    u = socket.create_connection(TARGET)
    threading.Thread(target=pipe, args=(c, u), daemon=True).start()
    threading.Thread(target=pipe, args=(u, c), daemon=True).start()
