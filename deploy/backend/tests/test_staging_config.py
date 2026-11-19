import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'staging_config.py'
spec = importlib.util.spec_from_file_location('staging_config', SCRIPT)
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)


class StagingConfigTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'backend.env'

    def test_missing_credentials_does_not_create_partial_settings(self):
        with self.assertRaises(ValueError):
            config.backend_env(self.path, {})
        self.assertFalse(self.path.exists())

    def test_partial_settings_preserve_existing_credentials(self):
        self.path.write_text('private-existing-settings', encoding='utf-8')
        with self.assertRaises(ValueError):
            config.backend_env(self.path, {'RDS_HOST': 'rds.example'})
        self.assertEqual(self.path.read_text(), 'private-existing-settings')
        config.backend_env(self.path, {})
        self.assertEqual(self.path.read_text(), 'private-existing-settings')

    def test_env_handles_literal_password_characters_and_uses_tls(self):
        config.backend_env(self.path, {'RDS_HOST': 'rds.example', 'RDS_PASSWORD': 'fake$%#"\\value'})
        text = self.path.read_text(encoding='utf-8')
        self.assertIn('/career?sslmode=require&ApplicationName=career-staging', text)
        self.assertIn('POSTGRES_USER="career"', text)
        self.assertIn('POSTGRES_PASSWORD="fake$%#\\"\\\\value"', text)
        if os.name == 'posix':
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_rejects_newline_injection_before_replacing_settings(self):
        self.path.write_text('original', encoding='utf-8')
        with self.assertRaises(ValueError):
            config.backend_env(self.path, {'RDS_HOST': 'rds.example', 'RDS_PASSWORD': 'fake\nSERVER_PORT=3000'})
        self.assertEqual(self.path.read_text(), 'original')

    def test_web_link_preserves_other_environment_values(self):
        self.path.write_text('# keep\nOTHER_SETTING=unchanged\nBACKEND_URL=old\nexport BACKEND_URL=also-old\n', encoding='utf-8')
        config.web_env(self.path)
        text = self.path.read_text(encoding='utf-8')
        self.assertIn('OTHER_SETTING=unchanged', text)
        self.assertEqual(text.count('BACKEND_URL='), 1)
        self.assertIn('BACKEND_URL=http://127.0.0.1:18081', text)
        config.web_env(self.path)
        self.assertEqual(self.path.read_text(encoding='utf-8'), text)

    def test_health_requires_actual_postings_not_only_up(self):
        def response(url):
            if url.endswith('/api/health'):
                return {'status': 'UP'}
            if 'postings?' in url:
                return {'totalElements': 0, 'content': []}
            return {'categories': list(range(10))}
        with patch.object(config, 'read_json', side_effect=response):
            with self.assertRaises(AssertionError):
                config.verify_backend()

    def test_web_verification_rejects_successful_dummy_only_response(self):
        with patch.object(config, 'read_json', side_effect=[{'categories': list(range(10))},
                         {'total': 6, 'jobs': [{'id': 'dummy:example'}]}]):
            with self.assertRaises(AssertionError):
                config.verify_web()
        with patch.object(config, 'read_json', side_effect=[{'categories': list(range(10))},
                         {'total': 200, 'jobs': [{'id': 'be:123'}]}]):
            self.assertEqual(config.verify_web()['backendJobsOnPage'], 1)

    def test_production_branch_is_rejected_before_any_deployment(self):
        bash = 'C:/Program Files/Git/bin/bash.exe' if os.name == 'nt' else 'bash'
        script = SCRIPT.with_name('deploy_staging.sh')
        result = subprocess.run([bash, str(script)], env={**os.environ, 'GITHUB_REF_NAME': 'main'}, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn(b'Only develop', result.stderr)


if __name__ == '__main__':
    unittest.main()
