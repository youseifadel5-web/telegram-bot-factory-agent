import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from apk_api_analyzer import analyze_apk, analyze_har, main


class AnalyzerTests(unittest.TestCase):
    def test_har_routes_and_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            har = Path(directory) / 'sample.har'
            har.write_text(json.dumps({'log': {'entries': [{
                'request': {'method': 'GET', 'url': 'https://example.test/api/movies?page=1', 'headers': [{'name': 'Authorization', 'value': 'redacted'}]},
                'response': {'status': 200, 'content': {'mimeType': 'application/json', 'text': '{"items":[{"id":1,"title":"X"}]}'}}
            }]}}), encoding='utf-8')
            out = analyze_har(har)
            route = out['routes']['GET /api/movies']
            self.assertEqual(route['query_parameters'], ['page'])
            self.assertEqual(route['response_schemas'][0]['properties']['items']['type'], 'array')

    def test_apk_candidates_and_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            apk = Path(directory) / 'app.apk'
            with zipfile.ZipFile(apk, 'w') as z:
                z.writestr('classes.dex', b'https://api.example.test/v1/movies /api/watch_links @GET("movies/{id}")')
                z.writestr('lib/arm64-v8a/libnative.so', b'iron x-iron-sig HMAC SHA256 nonce')
            out = analyze_apk(apk)
            self.assertIn('/api/watch_links', out['route_candidates'])
            self.assertTrue(out['native_libraries'][0]['signal_strings'])
            self.assertEqual(len(out['sha256']), 64)

    def test_cli_requires_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            har = Path(directory) / 'x.har'
            har.write_text('{"log":{"entries":[]}}', encoding='utf-8')
            with self.assertRaises(SystemExit) as error:
                main(['--har', str(har), '--out', str(Path(directory) / 'out.json')])
            self.assertEqual(error.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
