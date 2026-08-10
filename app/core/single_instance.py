from __future__ import annotations

import hashlib
import json
import logging
import os

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from app.core.external_activation import ExternalActivation

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())


class SingleInstanceCoordinator(QObject):
    activation_received = Signal(object)
    MAX_MESSAGE_BYTES = 16_384

    def __init__(self, server_name: str | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.server_name = server_name or self.default_server_name()
        self._server = QLocalServer(self)
        if hasattr(QLocalServer, "SocketOption"):
            self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self._server.newConnection.connect(self._accept_connections)
        self._buffers: dict[QLocalSocket, bytearray] = {}

    @staticmethod
    def default_server_name() -> str:
        identity = f"{os.environ.get('USERNAME', '')}|{os.environ.get('USERDOMAIN', '')}"
        suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        return f"Apson.YTDownloader.{suffix}"

    def listen(self) -> bool:
        if self._server.listen(self.server_name):
            return True
        QLocalServer.removeServer(self.server_name)
        return self._server.listen(self.server_name)

    def forward_to_running(
        self, activation: ExternalActivation | None, timeout_ms: int = 1200
    ) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self.server_name)
        if not socket.waitForConnected(timeout_ms):
            return False
        payload = {
            "action": "add" if activation and activation.url else "activate",
            "url": activation.url if activation else None,
            "auto_analyze": activation.auto_analyze if activation else False,
        }
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"
        if len(encoded) > self.MAX_MESSAGE_BYTES:
            return False
        accepted = socket.write(encoded) == len(encoded)
        socket.flush()
        if accepted and socket.waitForReadyRead(timeout_ms):
            accepted = bytes(socket.readAll()).strip() == b"OK"
        else:
            accepted = False
        socket.disconnectFromServer()
        return accepted

    @Slot()
    def _accept_connections(self) -> None:
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            if socket is None:
                continue
            self._buffers[socket] = bytearray()
            socket.readyRead.connect(lambda peer=socket: self._read_message(peer))
            socket.disconnected.connect(
                lambda peer=socket: self._forget_socket(peer)
            )
            if socket.bytesAvailable():
                self._read_message(socket)

    def _read_message(self, socket: QLocalSocket) -> None:
        buffer = self._buffers.setdefault(socket, bytearray())
        buffer.extend(bytes(socket.readAll()))
        if len(buffer) > self.MAX_MESSAGE_BYTES:
            socket.disconnectFromServer()
            return
        if b"\n" not in buffer:
            return
        data, _, remainder = buffer.partition(b"\n")
        buffer[:] = remainder
        try:
            payload = json.loads(data.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Nieprawidłowy komunikat IPC")
            action = payload.get("action")
            if action == "activate":
                activation = ExternalActivation()
            elif action == "add":
                activation = ExternalActivation(
                    ExternalActivation.validate_web_url(str(payload.get("url") or "")),
                    auto_analyze=bool(payload.get("auto_analyze", True)),
                )
            else:
                raise ValueError("Nieobsługiwana akcja IPC")
        except (UnicodeError, ValueError, json.JSONDecodeError):
            LOGGER.warning("Odrzucono nieprawidłowy komunikat pojedynczej instancji")
        else:
            self.activation_received.emit(activation)
            socket.write(b"OK\n")
            socket.flush()

    def _forget_socket(self, socket: QLocalSocket) -> None:
        self._buffers.pop(socket, None)
        try:
            socket.deleteLater()
        except RuntimeError:
            pass

    def close(self) -> None:
        self._server.close()
        QLocalServer.removeServer(self.server_name)
