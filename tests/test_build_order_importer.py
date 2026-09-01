import copy
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError

import yaml

from tools.build_orders import compiler
from tools.build_orders.compiler import BuildOrderValidationError, compile_directory


OVERLAY_BUILD = {
    "description": "",
    "civilization": "Knights Templar",
    "name": "2 TC",
    "author": "Perry",
    "source": "https://aoe4guides.com/builds/nlxHE4i1PhNNXqD2XTAP",
    "build_order": [
        {
            "age": 1,
            "population_count": -1,
            "time": "0:00",
            "villager_count": 6,
            "resources": {
                "food": 6,
                "wood": 0,
                "gold": 0,
                "stone": 0,
                "builder": -1,
            },
            "notes": [
                "6 @unit_worker/villager.webp@ on @resource/sheep.webp@",
                "@resource/rally.webp@ -&gt; @resource/resource_gold.webp@",
                "",
            ],
        },
        {
            "age": 2,
            "population_count": -1,
            "villager_count": -1,
            "resources": {
                "food": 0,
                "wood": 0,
                "gold": 0,
                "stone": 0,
                "builder": -1,
            },
            "notes": ["Build @building_economy/town-center.webp@"],
        },
    ],
    "video": "",
    "season": "Season 13",
    "map": None,
    "strategy": "Boom",
}


class BuildOrderImporterTests(unittest.TestCase):
    def test_file_import_emits_baseline_yaml_that_compiles(self) -> None:
        compiler_main = getattr(compiler, "main", None)
        if compiler_main is None:
            self.fail("tools.build_orders.compiler.main is missing")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "2 TC.bo"
            output = root / "templar_2tc.yaml"
            source.write_text(json.dumps(OVERLAY_BUILD), encoding="utf-8")

            self.assertEqual(
                compiler_main(["--import-file", str(source), "--output", str(output)]),
                0,
            )
            self.assertEqual(
                yaml.safe_load(output.read_text(encoding="utf-8")),
                {
                    "civ": "templar",
                    "title": "2 TC",
                    "link": "https://aoe4guides.com/builds/nlxHE4i1PhNNXqD2XTAP",
                    "steps": [
                        {
                            "title": "0:00",
                            "vils": {"food": 6},
                            "hints": [
                                "6 @unit_worker/villager.webp@ on @resource/sheep.webp@",
                                "@resource/rally.webp@ -> @resource/resource_gold.webp@",
                            ],
                        },
                        {
                            "hints": [
                                "Build @building_economy/town-center.webp@",
                            ],
                        },
                    ],
                },
            )

            catalog = compile_directory(root)
            self.assertEqual(len(catalog.build_orders), 1)
            self.assertEqual(catalog.build_orders[0].id, "templar-2-tc")

    def test_url_import_fetches_fixed_overlay_endpoint_and_emits_yaml(self) -> None:
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

            def read(self) -> bytes:
                return json.dumps(OVERLAY_BUILD).encode("utf-8")

        def open_url(request, timeout):
            requested_urls.append((request.full_url, timeout))
            return Response()

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "templar_2tc.yaml"
            with mock.patch(
                "tools.build_orders.compiler.urlopen",
                side_effect=open_url,
                create=True,
            ):
                try:
                    result = compiler.main(
                        [
                            "--import-url",
                            "https://aoe4guides.com/builds/nlxHE4i1PhNNXqD2XTAP",
                            "--output",
                            str(output),
                        ]
                    )
                except SystemExit as exc:
                    self.fail(f"compiler rejected URL import arguments: {exc}")

            self.assertEqual(result, 0)
            self.assertEqual(
                requested_urls,
                [
                    (
                        "https://aoe4guides.com/api/builds/nlxHE4i1PhNNXqD2XTAP?overlay=true",
                        30,
                    )
                ],
            )
            self.assertEqual(
                yaml.safe_load(output.read_text(encoding="utf-8"))["steps"][0]["hints"][1],
                "@resource/rally.webp@ -> @resource/resource_gold.webp@",
            )
            self.assertEqual(compile_directory(root).build_orders[0].id, "templar-2-tc")

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
                    translated = compiler.translate_overlay_document(document, "fixture.bo")
                except BuildOrderValidationError as exc:
                    self.fail(f"supported civilization was rejected: {exc}")
                self.assertEqual(translated["civ"], catalog_id)

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
                    compiler.translate_overlay_document(document, "fixture.bo")
                except BuildOrderValidationError as caught:
                    self.assertEqual(str(caught), expected)
                except Exception as exc:
                    self.fail(f"wrong exception type {type(exc).__name__}: {exc}")
                else:
                    self.fail("BuildOrderValidationError not raised")

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
                    compiler.translate_overlay_document(document, "fixture.bo")
                except BuildOrderValidationError as caught:
                    self.assertEqual(str(caught), expected)
                else:
                    self.fail("BuildOrderValidationError not raised")

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
                "tools.build_orders.compiler.urlopen",
                side_effect=AssertionError("network must not be called"),
            ):
                try:
                    compiler.fetch_overlay_document(url)
                except BuildOrderValidationError:
                    pass
                except Exception as exc:
                    self.fail(f"wrong exception type {type(exc).__name__}: {exc}")
                else:
                    self.fail("BuildOrderValidationError not raised")

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

        with mock.patch("tools.build_orders.compiler.urlopen", side_effect=response):
            try:
                compiler.fetch_overlay_document(page_url)
            except BuildOrderValidationError as caught:
                self.assertEqual(
                    str(caught),
                    f"{page_url}: aoe4guides build not found (HTTP 404)",
                )
            except Exception as exc:
                self.fail(f"wrong exception type {type(exc).__name__}: {exc}")
            else:
                self.fail("BuildOrderValidationError not raised")

    def test_remote_validation_errors_preserve_the_source_url(self) -> None:
        source_url = "https://aoe4guides.com/builds/nlxHE4i1PhNNXqD2XTAP"
        document = copy.deepcopy(OVERLAY_BUILD)
        document["civilization"] = 1

        with self.assertRaises(BuildOrderValidationError) as caught:
            compiler.translate_overlay_document(document, source_url)

        self.assertEqual(
            str(caught.exception),
            f"{source_url}: civilization: must be a non-empty string",
        )


if __name__ == "__main__":
    unittest.main()
