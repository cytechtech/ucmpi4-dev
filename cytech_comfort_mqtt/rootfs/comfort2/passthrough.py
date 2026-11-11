# Copyright (c) 2018 Khor Chin Heong (koochyrat@gmail.com)
# Copyright (c) 2025 Ingo de Jager (ingodejager@gmail.com)
# Copyright (c) 2026 Cytech Technology Pte Ltd
#
# Original project code by Khor Chin Heong.
# Modifications in 2025 by Ingo de Jager.
# Further modifications and enhancements in 2026 by Cytech Technology Pte Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


import logging
import socket
import threading
import time
import settings
import serial

logger = logging.getLogger(__name__)


class ComfortPassthroughServer:
    """
    Raw TCP-to-serial passthrough for Comfigurator.

    The normal Comfort bridge must release the serial port before
    passthrough opens it.
    """

    def __init__(
        self,
        host="0.0.0.0",
        port=10001,
        serial_port="/dev/serial0",
        baudrate=115200,
        on_start=None,
        on_stop=None,
        idle_timeout=300,
    ):
        self.host = host
        self.port = int(port)
        self.serial_port = serial_port
        self.baudrate = int(baudrate)
        self.on_start = on_start
        self.on_stop = on_stop
        self.idle_timeout = int(idle_timeout)

        self._thread = None
        self._stop_event = threading.Event()
        self._active_client = None
        self._server_socket = None
        self._client_lock = threading.Lock()
        self._listening = threading.Event()

    @property
    def listening(self):
        return self._listening.is_set()

    @property
    def client_connected(self):
        with self._client_lock:
            return self._active_client is not None

    def start(self):
        if self._thread and self._thread.is_alive():
            logger.warning("Comfort passthrough server already running")
            return

        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._run,
            name="comfort-passthrough-server",
            daemon=True,
        )
        self._thread.start()

        logger.info(
            "Comfort passthrough server started on %s:%s using %s at %s baud",
            self.host,
            self.port,
            self.serial_port,
            self.baudrate,
        )

    def stop(self):
        logger.info("Stopping Comfort passthrough server")

        self._stop_event.set()

        with self._client_lock:
            if self._active_client:
                try:
                    self._active_client.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass

                try:
                    self._active_client.close()
                except Exception:
                    pass

        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass

    def _run(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
                self._server_socket = server

                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server.bind((self.host, self.port))
                server.listen(1)
                server.settimeout(1.0)
                self._listening.set()

                while not self._stop_event.is_set():
                    try:
                        client, addr = server.accept()

                    except socket.timeout:
                        continue

                    except OSError:
                        break

                    with self._client_lock:
                        if self._active_client is not None:
                            logger.warning(
                                "Rejecting extra passthrough client from %s",
                                addr,
                            )
                            try:
                                client.close()
                            except Exception:
                                pass
                            continue

                        self._active_client = client

                    logger.warning(
                        "Comfigurator connected from %s:%s",
                        addr[0],
                        addr[1],
                    )

                    try:
                        self._handle_client(client)

                    except Exception:
                        logger.exception("Comfort passthrough session failed")

                    finally:
                        with self._client_lock:
                            self._active_client = None

                        logger.warning("Comfigurator disconnected")

        except Exception:
            logger.exception("Comfort passthrough server failed")

        finally:
            self._listening.clear()
            self._server_socket = None



    def _handle_client(self, client):
        client.settimeout(0.05)

        if not settings.PASSTHROUGH_ACTIVE:
            logger.warning(
                "Comfigurator TCP connection rejected because Comfigurator mode is not enabled"
            )
            try:
                client.close()
            except Exception:
                pass
            return
        started = False
        if self.on_start:
            self.on_start()
            started = True

        try:
            with serial.Serial(
                port=self.serial_port,
                baudrate=self.baudrate,
                timeout=0.05,
                write_timeout=0.5,
            ) as ser:
                logger.warning(
                    "Comfort serial passthrough active on %s at %s baud",
                    self.serial_port,
                    self.baudrate,
                )


                last_activity = time.time()

                while settings.PASSTHROUGH_ACTIVE and not self._stop_event.is_set():
                    activity = False

                    # TCP -> Comfort serial
                    try:
                        tcp_data = client.recv(1024)

                        if tcp_data:
                            ser.write(tcp_data)
                            activity = True
                        else:
                            logger.info("TCP client closed connection")
                            break

                    except socket.timeout:
                        pass

                    except OSError:
                        logger.info("TCP socket closed")
                        break

                    # Comfort serial -> TCP
                    try:
                        waiting = ser.in_waiting

                        if waiting:
                            serial_data = ser.read(waiting)

                            if serial_data:
                                client.sendall(serial_data)
                                activity = True

                    except serial.SerialException:
                        logger.exception("Serial passthrough error")
                        break

                    except OSError:
                        logger.info("TCP send failed")
                        break

                    if activity:
                        last_activity = time.time()

                    if time.time() - last_activity > self.idle_timeout:
                        logger.warning(
                            "Passthrough idle timeout after %s seconds",
                            self.idle_timeout,
                        )
                        break

                    time.sleep(0.005)

        finally:
            try:
                client.close()
            except Exception:
                pass

            if started and self.on_stop:
                self.on_stop()
