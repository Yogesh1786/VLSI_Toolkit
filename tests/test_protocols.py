"""Protocol checkers: APB, AHB-Lite, AXI-Stream, SPI, I2C, UART.   Run:  python -m unittest -v"""

import unittest
from collections import Counter
from pathlib import Path

from vlsi_toolkit import protocols

EX = Path(__file__).resolve().parent.parent / "examples"


def one(name):
    r = protocols.analyze_file(EX / "protocols" / name)
    assert len(r["interfaces"]) == 1, [i["protocol"] for i in r["interfaces"]]
    return r["interfaces"][0]


def rules(itf):
    return Counter(v["rule"] for v in itf["violations"])


class TestProtocols(unittest.TestCase):
    def test_apb(self):
        i = one("apb_demo.vcd")
        self.assertEqual(i["protocol"], "APB")
        self.assertEqual(rules(i), Counter({"APB_SLVERR": 1, "APB_ENABLE_WITHOUT_SETUP": 1, "APB_CHANGED_IN_ACCESS": 1, "APB_SETUP_NOT_FOLLOWED": 1}))
        read = next(t for t in i["transactions"] if t["addr"] == "0x04")
        self.assertEqual((read["kind"], read["data"], read["waits"]), ("READ", "0xA5A5A5A5", 2))

    def test_ahb_lite(self):
        i = one("ahb_lite_demo.vcd")
        self.assertEqual(rules(i), Counter({"AHB_BAD_INCREMENT": 1, "AHB_SEQ_WITHOUT_NONSEQ": 1, "AHB_1KB_BOUNDARY": 1,
                                            "AHB_CHANGED_IN_WAIT": 1, "AHB_ERROR_RESPONSE": 2, "AHB_BAD_ERROR_RESPONSE": 1}))
        first = i["transactions"][0]
        self.assertEqual((first["kind"], first["addr"], first["burst"], first["data"]), ("WRITE", "0x0100", "INCR4", "0x00001100"))

    def test_axi_stream(self):
        i = one("axi_stream_demo.vcd")
        self.assertEqual(rules(i), Counter({"AXIS_VALID_DROPPED": 1, "AXIS_PAYLOAD_CHANGED": 1, "AXIS_NULL_BYTES": 1, "AXIS_UNTERMINATED": 1}))
        self.assertEqual([p["beats"] for p in i["transactions"]], [4, 3, 3])
        self.assertEqual(i["transactions"][1]["bytes"], 10)            # last beat keeps 2 of 4 bytes

    def test_spi(self):
        i = one("spi_demo.vcd")
        self.assertEqual(rules(i), Counter({"SPI_PARTIAL_BYTE": 1, "SPI_CLOCK_WHILE_IDLE": 1}))
        self.assertEqual((i["transactions"][0]["mosi"], i["transactions"][0]["miso"], i["transactions"][0]["text"]), ("48 69", "00 01", "Hi"))
        self.assertEqual(i["stats"]["mode"], 0)

    def test_i2c(self):
        i = one("i2c_demo.vcd")
        self.assertEqual(rules(i), Counter({"I2C_ADDRESS_NACK": 1, "I2C_UNEXPECTED_CONDITION": 2, "I2C_NO_STOP": 1}))
        w = i["transactions"][0]
        self.assertEqual((w["kind"], w["addr"], w["data"], w["acks"]), ("WRITE", "0x50", "00 41 42", "AAA"))

    def test_uart(self):
        i = one("uart_demo.vcd")
        self.assertEqual(rules(i), Counter({"UART_FRAMING_ERROR": 1}))
        self.assertTrue(i["decoded_text"].startswith("Hello, VLSI!"))
        self.assertAlmostEqual(i["stats"]["baud"], 115200, delta=200)

    def test_no_false_interfaces_in_other_examples(self):
        for f in ("sample.vcd", "axi/axi_buggy.vcd", "axi/axi_clean.vcd"):
            self.assertEqual(protocols.analyze_file(EX / f)["interfaces"], [], f)

    def test_api(self):
        from fastapi.testclient import TestClient
        from api.main import app
        r = TestClient(app).post("/api/verif/protocols", json={"name": "u.vcd", "text": (EX / "protocols/uart_demo.vcd").read_text()})
        self.assertEqual(r.json()["interfaces"][0]["protocol"], "UART")


if __name__ == "__main__":
    unittest.main()
