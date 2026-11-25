import io
import json
import unittest
from unittest.mock import patch
from app.core import check_github_app_update


class DistributionTests(unittest.TestCase):
    @patch('app.platforms.architecture', return_value='x64')
    @patch('app.platforms.system', return_value='Windows')
    @patch('app.core.urllib.request.urlopen')
    def test_release_update(self, request, system, arch):
        name = 'Vocaflop-9.0.0-Windows-x64-Setup.exe'
        release = {'tag_name': 'v9.0.0', 'assets': [{'name': name}, {'name': 'SHA256SUMS.txt'}]}
        request.side_effect = [io.BytesIO(json.dumps(release).encode()), io.BytesIO(f'{"a" * 64}  {name}\n'.encode())]
        result = check_github_app_update()
        self.assertEqual(result['sha256'], 'a' * 64)
        self.assertTrue(result['url'].endswith(name))

    @patch('app.core.urllib.request.urlopen')
    def test_prerelease_ignored(self, request):
        request.return_value = io.BytesIO(b'{"tag_name":"v9.0.0","prerelease":true}')
        self.assertIsNone(check_github_app_update())
