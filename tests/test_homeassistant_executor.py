import unittest
from unittest import mock

from novaadapt_core.homeassistant_executor import DirectMQTTExecutor


class _FakeMQTTSocket:
    def __init__(self):
        self.sent = []
        self._recv = bytearray(b"\x20\x02\x00\x00")
        self.closed = False
        self.timeout = None

    def sendall(self, payload):
        self.sent.append(bytes(payload))

    def recv(self, size):
        if not self._recv:
            return b""
        chunk = self._recv[:size]
        del self._recv[:size]
        return bytes(chunk)

    def settimeout(self, timeout):
        self.timeout = timeout

    def close(self):
        self.closed = True


class DirectMQTTExecutorTests(unittest.TestCase):
    def test_status_reports_ok_when_broker_accepts_connection(self):
        fake_socket = _FakeMQTTSocket()
        executor = DirectMQTTExecutor(broker_url="mqtt://broker.local:1883", client_id="novaadapt-test")

        with mock.patch("novaadapt_core.homeassistant_executor.socket.create_connection", return_value=fake_socket):
            status = executor.status()

        self.assertTrue(status["ok"])
        self.assertEqual(status["transport"], "mqtt-direct")
        self.assertEqual(status["host"], "broker.local")
        self.assertEqual(status["port"], 1883)
        self.assertTrue(fake_socket.closed)
        self.assertTrue(fake_socket.sent)
        self.assertEqual(fake_socket.sent[0][0], 0x10)
        self.assertEqual(fake_socket.sent[-1], b"\xe0\x00")

    def test_publish_sends_topic_and_payload(self):
        fake_socket = _FakeMQTTSocket()
        executor = DirectMQTTExecutor(
            broker_url="mqtt://broker.local:1883",
            client_id="novaadapt-test",
            username="user",
            password="pass",
        )

        with mock.patch("novaadapt_core.homeassistant_executor.socket.create_connection", return_value=fake_socket):
            result = executor.publish(topic="novaadapt/test", payload="ping", retain=True)

        self.assertEqual(result["transport"], "mqtt-direct")
        self.assertEqual(result["topic"], "novaadapt/test")
        self.assertEqual(result["payload_size"], 4)
        self.assertTrue(result["retain"])
        self.assertGreaterEqual(len(fake_socket.sent), 3)
        publish_packet = fake_socket.sent[1]
        self.assertEqual(publish_packet[0] & 0x31, 0x31)
        self.assertIn(b"novaadapt/test", publish_packet)
        self.assertTrue(publish_packet.endswith(b"ping"))

    def test_publish_rejects_qos_above_zero(self):
        executor = DirectMQTTExecutor(broker_url="mqtt://broker.local:1883")
        with self.assertRaises(ValueError):
            executor.publish(topic="novaadapt/test", payload="ping", qos=1)
