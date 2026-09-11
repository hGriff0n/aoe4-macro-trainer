import copy
import json
import tempfile
import unittest
from http.client import IncompleteRead
from io import BytesIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest import mock
from urllib.error import HTTPError

from tests.build_order_import_fixtures import OVERLAY_BUILD
from tools.build_orders.compiler import compile_document
from tools.build_orders.importer import (
    ImportValidationError,
    fetch_overlay_document,
    read_overlay_file,
    render_overlay_note,
    translate_overlay_document,
)


class BuildOrderImporterTests(unittest.TestCase):
    def test_file_import_translates_baseline_mapping_that_compiles(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "2 TC.bo"
            source.write_text(json.dumps(OVERLAY_BUILD), encoding="utf-8")

            translated = translate_overlay_document(read_overlay_file(source), source)
            self.assertEqual(
                translated,
                {
                    "civ": "templar",
                    "title": "2 TC",
                    "link": "https://aoe4guides.com/builds/nlxHE4i1PhNNXqD2XTAP",
                    "steps": [
                        {
                            "title": "0:00",
                            "vils": {"food": 6},
                            "hints": [
                                "6 Villager on Sheep",
                                "Rally -> Gold",
                            ],
                        },
                        {
                            "hints": [
                                "Build Town Center",
                            ],
                        },
                    ],
                },
            )
            self.assertEqual(compile_document(translated, source).id, "templar-2-tc")

    def test_url_import_fetches_fixed_overlay_endpoint_and_compiles_mapping(self) -> None:
        requested_urls = []

        class Response:
            status = 200
            headers = {
                "Content-Type": "application/json; charset=utf-8",
                "Cache-Control": "public, max-age=245",
            }

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self, size=-1) -> bytes:
                return json.dumps(OVERLAY_BUILD).encode("utf-8")

        def open_url(request, timeout):
            requested_urls.append((request.full_url, timeout))
            return Response()

        class Opener:
            def open(self, request, timeout):
                return open_url(request, timeout)

        with tempfile.TemporaryDirectory() as temp:
            with mock.patch(
                "tools.build_orders.importer.build_overlay_opener",
                return_value=Opener(),
            ):
                document = fetch_overlay_document(
                    "https://aoe4guides.com/builds/nlxHE4i1PhNNXqD2XTAP"
                )

            self.assertEqual(
                requested_urls,
                [
                    (
                        "https://aoe4guides.com/api/builds/nlxHE4i1PhNNXqD2XTAP?overlay=true",
                        30,
                    )
                ],
            )
            translated = translate_overlay_document(document, "sample.bo")
            self.assertEqual(translated["steps"][0]["hints"][1], "Rally -> Gold")
            self.assertEqual(compile_document(translated, "sample.bo").id, "templar-2-tc")

    def test_translated_mapping_compiles_without_a_yaml_round_trip(self) -> None:
        translated = translate_overlay_document(copy.deepcopy(OVERLAY_BUILD), "sample.bo")

        order = compile_document(translated, "sample.bo")

        self.assertEqual(order.id, "templar-2-tc")
        self.assertEqual(order.civ, "templar")
        self.assertEqual(order.steps[0].checks[0].kind, "vils")

    def test_maps_every_rts_overlay_civilization_to_catalog_id(self) -> None:
        expected = {
            "Abbasid Dynasty": "abbasid",
            "Ayyubids": "ayyubids",
            "Byzantines": "byzantines",
            "Chinese": "chinese",
            "Delhi Sultanate": "delhi",
            "English": "english",
            "French": "french",
            "Golden Horde": "golden_horde",
            "House of Lancaster": "house_of_lancaster",
            "Holy Roman Empire": "hre",
            "Japanese": "japanese",
            "Jeanne d'Arc": "jeanne_darc",
            "Jin Dynasty": "jin_dynasty",
            "Knights Templar": "templar",
            "Macedonian Dynasty": "macedonian_dynasty",
            "Malians": "malians",
            "Mongols": "mongols",
            "Order of the Dragon": "order_of_the_dragon",
            "Ottomans": "ottomans",
            "Rus": "rus",
            "Sengoku Daimyo": "sengoku_daimyo",
            "Tughlaq Dynasty": "tughlaq_dynasty",
            "Zhu Xi's Legacy": "zhu_xi",
        }

        for display_name, catalog_id in expected.items():
            with self.subTest(display_name=display_name):
                document = copy.deepcopy(OVERLAY_BUILD)
                document["civilization"] = display_name
                try:
                    translated = translate_overlay_document(document, "fixture.bo")
                except ImportValidationError as exc:
                    self.fail(f"supported civilization was rejected: {exc}")
                self.assertEqual(translated["civ"], catalog_id)

    def test_renders_overlay_note_tokens_as_readable_text_with_spacing(self) -> None:
        document = copy.deepcopy(OVERLAY_BUILD)
        document["build_order"][0]["notes"] = [
            "6 @unit_worker/villager.webp@ on "
            "@resource/resource_gold.webp@@unit_worker/villager.webp@ -> "
            "@building_economy/town-center.webp@ &amp; "
            "@technology_templar/safe_passage.webp@"
        ]

        translated = translate_overlay_document(document, "fixture.bo")

        self.assertEqual(
            translated["steps"][0]["hints"],
            ["6 Villager on Gold Villager -> Town Center & Safe Passage"],
        )

    def test_renders_known_opaque_tokens_and_falls_back_for_unknown_tokens(self) -> None:
        document = copy.deepcopy(OVERLAY_BUILD)
        document["build_order"][0]["notes"] = [
            "@civilization_flag/hos.webp@, "
            "@resource/gaiatreeprototypetree.webp@, "
            "@resource/berrybush.webp@, "
            "@technology_templar/safepassage.webp@, "
            "@custom/siege-workshop_mk2.webp@."
        ]

        translated = translate_overlay_document(document, "fixture.bo")

        self.assertEqual(
            translated["steps"][0]["hints"],
            [
                "House of Lancaster, Tree, Berry Bush, Safe Passage, "
                "Siege Workshop Mk2."
            ],
        )

    def test_renders_adjacent_civilization_tokens_from_downloaded_sample(self) -> None:
        document = copy.deepcopy(OVERLAY_BUILD)
        document["build_order"][0]["notes"] = [
            "Build @building_military/barracks.webp@ "
            "(If @civilization_flag/eng.webp@ build "
            "@building_military/stable.webp@, elif "
            "@civilization_flag/mon.webp@@civilization_flag/ayy.webp@ build "
            "@building_military/archery-range.webp@)"
        ]

        translated = translate_overlay_document(document, "2 TC.bo")

        self.assertEqual(
            translated["steps"][0]["hints"],
            [
                "Build Barracks (If English build Stable, elif "
                "Mongols Ayyubids build Archery Range)"
            ],
        )

    def test_rejects_malformed_overlay_fields_with_source_paths(self) -> None:
        cases = [
            (
                "boolean age",
                lambda document: document["build_order"][0].__setitem__("age", True),
                "fixture.bo: build_order[0].age: must be an integer",
            ),
            (
                "invalid time",
                lambda document: document["build_order"][0].__setitem__("time", "1:99"),
                "fixture.bo: build_order[0].time: must use M:SS time format",
            ),
            (
                "negative food",
                lambda document: document["build_order"][0]["resources"].__setitem__("food", -1),
                "fixture.bo: build_order[0].resources.food: must be a non-negative integer",
            ),
            (
                "non-string note",
                lambda document: document["build_order"][0]["notes"].__setitem__(0, 6),
                "fixture.bo: build_order[0].notes[0]: must be a string",
            ),
            (
                "unknown step field",
                lambda document: document["build_order"][0].__setitem__("instruction", "build house"),
                "fixture.bo: build_order[0].instruction: unknown field",
            ),
            (
                "untranslatable step",
                lambda document: document["build_order"][1].__setitem__("notes", []),
                "fixture.bo: build_order[1]: has no translatable checks or hints",
            ),
        ]

        for label, mutate, expected in cases:
            with self.subTest(label=label):
                document = copy.deepcopy(OVERLAY_BUILD)
                mutate(document)
                try:
                    translate_overlay_document(document, "fixture.bo")
                except ImportValidationError as caught:
                    self.assertEqual(str(caught), expected)
                except Exception as exc:
                    self.fail(f"wrong exception type {type(exc).__name__}: {exc}")
                else:
                    self.fail("ImportValidationError not raised")

    def test_validates_required_and_optional_overlay_metadata(self) -> None:
        cases = [
            (
                "missing description",
                lambda document: document.pop("description"),
                "fixture.bo: description: must be a string",
            ),
            (
                "invalid optional strategy",
                lambda document: document.__setitem__("strategy", ["Boom"]),
                "fixture.bo: strategy: must be a string or null",
            ),
            (
                "unknown root field",
                lambda document: document.__setitem__("language", "en"),
                "fixture.bo: language: unknown field",
            ),
        ]

        for label, mutate, expected in cases:
            with self.subTest(label=label):
                document = copy.deepcopy(OVERLAY_BUILD)
                mutate(document)
                try:
                    translate_overlay_document(document, "fixture.bo")
                except ImportValidationError as caught:
                    self.assertEqual(str(caught), expected)
                else:
                    self.fail("ImportValidationError not raised")

    def test_url_import_rejects_untrusted_or_malformed_urls_before_network(self) -> None:
        invalid_urls = [
            "http://aoe4guides.com/builds/abc",
            "https://aoe4guides.com.evil.example/builds/abc",
            "https://aoe4guides.com:invalid/builds/abc",
            "https://aoe4guides.com/users/abc",
            "https://aoe4guides.com/builds/a%2Fb",
        ]

        for url in invalid_urls:
            with self.subTest(url=url), mock.patch(
                "tools.build_orders.importer.build_overlay_opener",
                side_effect=AssertionError("network must not be called"),
            ):
                try:
                    fetch_overlay_document(url)
                except ImportValidationError:
                    pass
                except Exception as exc:
                    self.fail(f"wrong exception type {type(exc).__name__}: {exc}")
                else:
                    self.fail("ImportValidationError not raised")

    def test_url_import_reports_not_found_without_using_blank_api_reason(self) -> None:
        page_url = "https://aoe4guides.com/builds/missing"
        api_url = "https://aoe4guides.com/api/builds/missing?overlay=true"
        response = HTTPError(
            api_url,
            404,
            "Not Found",
            {"Content-Type": "application/json"},
            BytesIO(b'{"reason":""}'),
        )

        opener = mock.Mock()
        opener.open.side_effect = response
        with mock.patch("tools.build_orders.importer.build_overlay_opener", return_value=opener):
            try:
                fetch_overlay_document(page_url)
            except ImportValidationError as caught:
                self.assertEqual(
                    str(caught),
                    f"{page_url}: aoe4guides build not found (HTTP 404)",
                )
            except Exception as exc:
                self.fail(f"wrong exception type {type(exc).__name__}: {exc}")
            else:
                self.fail("ImportValidationError not raised")

    def test_url_import_rejects_oversized_responses(self) -> None:
        page_url = "https://aoe4guides.com/builds/oversized"

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self, size=-1):
                return b"x" * size

        opener = mock.Mock()
        opener.open.return_value = Response()
        with mock.patch("tools.build_orders.importer.build_overlay_opener", return_value=opener):
            with self.assertRaises(ImportValidationError) as caught:
                fetch_overlay_document(page_url)

        self.assertEqual(
            str(caught.exception),
            f"{page_url}: aoe4guides response exceeds 2097152 bytes",
        )

    def test_url_import_reports_invalid_utf8_as_validation_error(self) -> None:
        page_url = "https://aoe4guides.com/builds/invalid-utf8"

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self, size=-1):
                return b"\xff"

        opener = mock.Mock()
        opener.open.return_value = Response()
        with mock.patch("tools.build_orders.importer.build_overlay_opener", return_value=opener):
            with self.assertRaises(ImportValidationError) as caught:
                fetch_overlay_document(page_url)

        self.assertIn(
            f"{page_url}: aoe4guides returned non-UTF-8 data:",
            str(caught.exception),
        )

    def test_url_import_reports_truncated_response_as_validation_error(self) -> None:
        page_url = "https://aoe4guides.com/builds/truncated"

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self, size=-1):
                raise IncompleteRead(b'{"partial":', 10)

        opener = mock.Mock()
        opener.open.return_value = Response()
        with mock.patch("tools.build_orders.importer.build_overlay_opener", return_value=opener):
            with self.assertRaises(ImportValidationError) as caught:
                fetch_overlay_document(page_url)

        self.assertIn(
            f"{page_url}: aoe4guides response was interrupted:",
            str(caught.exception),
        )

    def test_file_read_errors_preserve_the_source_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "missing.bo"
            with self.assertRaises(ImportValidationError) as caught:
                read_overlay_file(missing)

        self.assertIn(f"{missing}: unable to read overlay JSON:", str(caught.exception))

    def test_remote_validation_errors_preserve_the_source_url(self) -> None:
        source_url = "https://aoe4guides.com/builds/nlxHE4i1PhNNXqD2XTAP"
        document = copy.deepcopy(OVERLAY_BUILD)
        document["civilization"] = 1

        with self.assertRaises(ImportValidationError) as caught:
            translate_overlay_document(document, source_url)

        self.assertEqual(
            str(caught.exception),
            f"{source_url}: civilization: must be a non-empty string",
        )

    def test_overlay_http_opener_rejects_redirects_before_contacting_target(self) -> None:
        from tools.build_orders.importer import build_overlay_opener

        opener_factory = build_overlay_opener
        if opener_factory is None:
            self.fail("tools.build_orders.importer.build_overlay_opener is missing")

        target_hits = []

        class TargetHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                target_hits.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, format, *args):
                pass

        target_server = ThreadingHTTPServer(("127.0.0.1", 0), TargetHandler)
        target_url = f"http://127.0.0.1:{target_server.server_port}/target"

        class RedirectHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", target_url)
                self.end_headers()

            def log_message(self, format, *args):
                pass

        redirect_server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
        threads = [
            Thread(target=target_server.serve_forever, daemon=True),
            Thread(target=redirect_server.serve_forever, daemon=True),
        ]
        for thread in threads:
            thread.start()

        try:
            redirect_url = f"http://127.0.0.1:{redirect_server.server_port}/redirect"
            with self.assertRaises(HTTPError) as caught:
                opener_factory().open(redirect_url, timeout=2)
            self.assertEqual(caught.exception.code, 302)
            self.assertEqual(target_hits, [])
        finally:
            redirect_server.shutdown()
            target_server.shutdown()
            redirect_server.server_close()
            target_server.server_close()
            for thread in threads:
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
