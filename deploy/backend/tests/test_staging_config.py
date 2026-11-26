import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import io
from urllib.parse import urlsplit, unquote
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'staging_config.py'
spec = importlib.util.spec_from_file_location('staging_config', SCRIPT)
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)


class StagingConfigTest(unittest.TestCase):
    def profile_settings(self):
        return {'GITHUB_REF_NAME':'develop','RDS_HOST':'rds.example','RDS_USERNAME':'app-user','RDS_PASSWORD':'fake$%#"\\value','RDS_DATABASE':'career'}

    def test_profile_env_preserves_web_settings_and_encodes_credentials(self):
        self.path.write_text('BACKEND_URL=http://127.0.0.1:18081\nKAKAO_REST_API_KEY=keep-existing\n',encoding='utf-8')
        ca=Path(self.temp.name)/'rds-ca.pem'
        with patch.object(config.urllib.request,'urlopen',return_value=io.BytesIO(b'-----BEGIN CERTIFICATE-----\nfixture\n-----END CERTIFICATE-----')):
            config.profile_env(self.path,ca,self.profile_settings())
        values={key:json.loads(value) if value.startswith('"') else value for key,value in (line.split('=',1) for line in self.path.read_text().splitlines())}
        connection=urlsplit(values['CAREER_PROFILE_DATABASE_URL'])
        self.assertEqual(unquote(connection.password),self.profile_settings()['RDS_PASSWORD'])
        self.assertEqual(values['CAREER_PROFILE_NAMESPACE'],'staging')
        self.assertEqual(values['CAREER_ACCOUNT_STORE'],'rds')
        self.assertEqual(values['CAREER_DATA_DIR'],str(self.path.parent.resolve()))
        self.assertEqual(values['BACKEND_URL'],'http://127.0.0.1:18081')
        self.assertEqual(values['KAKAO_REST_API_KEY'],'keep-existing')
        self.assertTrue(ca.exists())

    def test_profile_env_configures_kakao_without_printing_keys(self):
        settings = {**self.profile_settings(), 'KAKAO_REST_API_KEY':'test-key', 'KAKAO_CLIENT_SECRET':'test-secret',
                    'KAKAO_REDIRECT_URI':'https://staging.example.test/api/auth/kakao/callback'}
        with patch.object(config.urllib.request,'urlopen',return_value=io.BytesIO(b'-----BEGIN CERTIFICATE-----\nfixture\n-----END CERTIFICATE-----')):
            config.profile_env(self.path,Path(self.temp.name)/'ca.pem',settings)
        values={key:json.loads(value) for key,value in (line.split('=',1) for line in self.path.read_text().splitlines())}
        self.assertEqual(values['KAKAO_CLIENT_SECRET'],'test-secret')
        self.assertEqual(values['KAKAO_REDIRECT_URI'],settings['KAKAO_REDIRECT_URI'])
        for patch_values in ({'KAKAO_CLIENT_SECRET':''},{'KAKAO_REDIRECT_URI':'http://localhost/callback'}):
            with patch.object(config.urllib.request,'urlopen',return_value=io.BytesIO(b'-----BEGIN CERTIFICATE-----\nfixture\n-----END CERTIFICATE-----')):
                with self.assertRaises(ValueError):
                    config.profile_env(self.path,Path(self.temp.name)/'ca.pem',{**settings,**patch_values})

    def test_profile_env_rejects_production_and_partial_or_multiline_settings(self):
        self.path.write_text('original')
        for patch_values in ({'GITHUB_REF_NAME':'main'},{'RDS_USERNAME':''},{'RDS_PASSWORD':'fake\nOTHER=value'}):
            with self.assertRaises(ValueError):
                config.profile_env(self.path,Path(self.temp.name)/'ca.pem',{**self.profile_settings(),**patch_values})
            self.assertEqual(self.path.read_text(),'original')

    def test_profile_env_rejects_invalid_certificate_without_replacing_settings(self):
        self.path.write_text('original')
        with patch.object(config.urllib.request,'urlopen',return_value=io.BytesIO(b'not a certificate')):
            with self.assertRaises(ValueError):config.profile_env(self.path,Path(self.temp.name)/'ca.pem',self.profile_settings())
        self.assertEqual(self.path.read_text(),'original')

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

    def test_system_status_requires_actual_postings_not_only_up(self):
        def response(url):
            if url.endswith('/api/system/status'):
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

    def test_startup_diagnostics_hide_credentials_and_database_addresses(self):
        environment = {'RDS_PASSWORD': 'fake-secret-123', 'RDS_HOST': 'private.db.example', 'RDS_USERNAME': 'test-user'}
        text = 'INFO regular startup\nERROR password fake-secret-123 host private.db.example user test-user\nCaused by: connection jdbc:postgresql://private.db.example/career?password=fake-secret-123\nFATAL authentication failed'
        result = '\n'.join(config.sanitized_causes(text, environment))
        for value in environment.values():
            self.assertNotIn(value, result)
        self.assertNotIn('regular startup', result)
        self.assertIn('FATAL authentication failed', result)
        self.assertNotIn('jdbc:postgresql://', result)

    def test_startup_diagnostics_are_bounded(self):
        self.assertEqual(len(config.sanitized_causes('\n'.join('ERROR failure' for _ in range(100)), {})), 20)

    def test_web_readiness_waits_for_real_backend_rows(self):
        with patch.object(config, 'verify_web', side_effect=[AssertionError(), OSError(), {'backendJobsOnPage': 24}]) as verify:
            with patch.object(config.time, 'sleep') as sleep:
                result = config.wait_for_web()
        self.assertEqual(result, {'backendJobsOnPage': 24, 'verificationAttempt': 3})
        self.assertEqual(verify.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_web_readiness_still_fails_if_backend_never_appears(self):
        with patch.object(config, 'verify_web', side_effect=AssertionError('No backend rows')) as verify:
            with patch.object(config.time, 'sleep'):
                with self.assertRaises(AssertionError):
                    config.wait_for_web()
        self.assertEqual(verify.call_count, 4)


if __name__ == '__main__':
    unittest.main()
