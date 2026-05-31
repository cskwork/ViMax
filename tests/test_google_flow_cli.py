import importlib.util
import json
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "google-flow-video"
    / "scripts"
    / "google_flow_cli.py"
)
SPEC = importlib.util.spec_from_file_location("google_flow_cli", MODULE_PATH)
google_flow_cli = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(google_flow_cli)


class GoogleFlowCliTests(unittest.TestCase):
    def test_video_ready_rejects_existing_source(self):
        old_src = "https://labs.google/fx/api/trpc/media.old"
        status = {
            "generating": False,
            "videos": 1,
            "src": old_src,
            "video_srcs": [old_src],
            "dur": 8,
        }

        self.assertEqual(google_flow_cli._video_sources(status), {old_src})
        self.assertFalse(google_flow_cli._video_ready(status, {old_src}))

    def test_video_ready_selects_new_source(self):
        old_src = "https://labs.google/fx/api/trpc/media.old"
        new_src = "https://labs.google/fx/api/trpc/media.new"
        status = {
            "generating": False,
            "videos": 2,
            "src": old_src,
            "video_srcs": [old_src, new_src],
            "dur": 8,
        }

        self.assertTrue(google_flow_cli._video_ready(status, {old_src}))
        self.assertEqual(google_flow_cli._new_video_src(status, {old_src}), new_src)

    def test_download_js_targets_selected_source(self):
        src = "https://labs.google/fx/api/trpc/media.new?name=abc"

        js = google_flow_cli._download_js(src)

        self.assertIn(json.dumps(src), js)
        self.assertIn("page.context().request.get(src)", js)


if __name__ == "__main__":
    unittest.main()
