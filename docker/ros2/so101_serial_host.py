"""Forward one macOS serial port to a local TCP client without motor commands."""

import argparse
import socket
import threading

import serial


def forward(device: str, baudrate: int, client: socket.socket) -> None:
    stop = threading.Event()
    with serial.Serial(device, baudrate=baudrate, timeout=0.1, write_timeout=1, exclusive=True) as port:
        print(f"Connected to {device} at {baudrate} baud", flush=True)

        def serial_to_tcp() -> None:
            try:
                while not stop.is_set():
                    first_byte = port.read(1)
                    if first_byte:
                        client.sendall(first_byte + port.read(port.in_waiting))
            except (OSError, serial.SerialException):
                stop.set()
                try:
                    client.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

        reader = threading.Thread(target=serial_to_tcp, daemon=True)
        reader.start()
        client.settimeout(0.2)
        try:
            while not stop.is_set():
                try:
                    data = client.recv(4096)
                except socket.timeout:
                    continue
                if not data:
                    break
                port.write(data)
        finally:
            stop.set()
            reader.join(timeout=1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True, help="macOS /dev/cu.usbmodem... path")
    parser.add_argument("--baudrate", type=int, default=1_000_000)
    parser.add_argument("--port", type=int, default=54321)
    args = parser.parse_args()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", args.port))
        server.listen(1)
        print(f"Waiting for Jetson container on 127.0.0.1:{args.port}", flush=True)
        while True:
            client, _ = server.accept()
            with client:
                try:
                    client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    forward(args.device, args.baudrate, client)
                except (OSError, serial.SerialException) as exc:
                    print(f"Serial bridge disconnected: {exc}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Serial bridge stopped")
