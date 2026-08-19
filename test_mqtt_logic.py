import json
import unittest
from mqtt_logic import *


class LogicTests(unittest.TestCase):
    def test_topics(self):
        self.assertEqual(json_subscription("/msh/LZ/"), "msh/LZ/2/json/#")
        self.assertEqual(json_downlink_topic("msh/LZ", "LZMesh", "!7efeee00"),
                         "msh/LZ/2/json/LZMesh/!7efeee00")

    def test_envelope(self):
        body = json.loads(sendtext_envelope(123, "hello", 1))
        self.assertEqual(body, {"from":123, "channel":1, "type":"sendtext", "payload":"hello"})

    def test_parse(self):
        msg = parse_json_message("msh/LZ/2/json/LZMesh/!1234abcd",
            b'{"from":305441741,"type":"text","payload":{"text":"Hi"},"timestamp":10}')
        self.assertEqual(msg.text, "Hi")
        self.assertEqual(msg.gateway_id, "!1234abcd")

    def test_unknown_packet_is_visible(self):
        msg = parse_json_message("msh/LZ/2/json/LZMesh/!1234abcd",
            b'{"from":305441741,"sender":"!1234abcd","foo":42}')
        self.assertEqual(msg.message_type, "unknown")
        self.assertEqual(msg.text, '{"foo":42}')

    def test_infers_nodeinfo(self):
        msg = parse_json_message("msh/LZ/2/json/LZMesh/!1234abcd",
            b'{"payload":{"longname":"Joplin Gateway","shortname":"JPG"}}')
        self.assertEqual(msg.message_type, "nodeinfo")
        self.assertEqual(msg.text, "Joplin Gateway")

    def test_direct_message_reachability(self):
        self.assertTrue(direct_message_reachable(None))
        self.assertTrue(direct_message_reachable({}))
        self.assertTrue(direct_message_reachable({"hops": 0}))
        self.assertTrue(direct_message_reachable({"hops": 1}))
        self.assertFalse(direct_message_reachable({"hops": 2}))
        self.assertFalse(direct_message_reachable({"hops": 4}))


if __name__ == "__main__": unittest.main()
