"""
Tests for Agent 4 — Security Scanner
Validates secret detection and OWASP pattern matching.
"""

import pytest
from agents.security_scanner.security_scanner import SecurityScannerAgent, _redact_line


class TestSecretDetection:
    def setup_method(self):
        self.agent = SecurityScannerAgent()

    @pytest.mark.asyncio
    async def test_detects_hardcoded_api_key(self, tmp_path):
        f = tmp_path / "config.py"
        f.write_text('api_key = "sk-live-abc123XYZlongvalue"\n')
        manifest = [{"relative_path": "config.py", "language": "Python"}]
        issues = await self.agent._detect_secrets(str(tmp_path), manifest)
        assert any("API Key" in i["title"] or "Secret" in i["title"] for i in issues)

    @pytest.mark.asyncio
    async def test_ignores_placeholder_values(self, tmp_path):
        f = tmp_path / "config.py"
        f.write_text('api_key = "your_key_here"\n')
        manifest = [{"relative_path": "config.py", "language": "Python"}]
        issues = await self.agent._detect_secrets(str(tmp_path), manifest)
        # Short placeholder shouldn't match (< 20 chars pattern threshold)
        api_issues = [i for i in issues if "API" in i.get("title", "")]
        assert len(api_issues) == 0

    @pytest.mark.asyncio
    async def test_detects_github_token(self, tmp_path):
        f = tmp_path / "deploy.py"
        f.write_text('token = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"\n')
        manifest = [{"relative_path": "deploy.py", "language": "Python"}]
        issues = await self.agent._detect_secrets(str(tmp_path), manifest)
        assert any("GitHub" in i["title"] for i in issues)

    @pytest.mark.asyncio
    async def test_commented_secret_not_flagged(self, tmp_path):
        f = tmp_path / "config.py"
        f.write_text('# api_key = "sk-live-abc123XYZlongvalue"\n')
        manifest = [{"relative_path": "config.py", "language": "Python"}]
        issues = await self.agent._detect_secrets(str(tmp_path), manifest)
        assert len(issues) == 0


class TestOWASPPatterns:
    def setup_method(self):
        self.agent = SecurityScannerAgent()

    @pytest.mark.asyncio
    async def test_detects_eval_injection(self, tmp_path):
        f = tmp_path / "app.py"
        f.write_text('result = eval(user_input)\n')
        manifest = [{"relative_path": "app.py", "language": "Python"}]
        issues = await self.agent._regex_owasp_scan(str(tmp_path), manifest)
        assert any("Injection" in i["title"] or "A03" in i["title"] for i in issues)

    @pytest.mark.asyncio
    async def test_detects_debug_mode(self, tmp_path):
        f = tmp_path / "app.py"
        f.write_text('app.run(debug=True)\n')
        manifest = [{"relative_path": "app.py", "language": "Python"}]
        issues = await self.agent._regex_owasp_scan(str(tmp_path), manifest)
        assert any("A04" in i["title"] or "Misconfiguration" in i["title"] for i in issues)

    @pytest.mark.asyncio
    async def test_detects_pickle_loads(self, tmp_path):
        f = tmp_path / "model.py"
        f.write_text('model = pickle.loads(data)\n')
        manifest = [{"relative_path": "model.py", "language": "Python"}]
        issues = await self.agent._regex_owasp_scan(str(tmp_path), manifest)
        assert any("A08" in i["title"] or "Integrity" in i["title"] for i in issues)

    @pytest.mark.asyncio
    async def test_detects_ssl_verify_false(self, tmp_path):
        f = tmp_path / "client.py"
        f.write_text('requests.get(url, verify=False)\n')
        manifest = [{"relative_path": "client.py", "language": "Python"}]
        issues = await self.agent._regex_owasp_scan(str(tmp_path), manifest)
        assert any("A05" in i["title"] or "Misconfiguration" in i["title"] for i in issues)


class TestRedactLine:
    def test_redacts_middle_of_secret(self):
        line = 'api_key = "abcd1234567890efgh"'
        redacted = _redact_line(line)
        assert "1234567890" not in redacted

    def test_preserves_short_strings(self):
        line = 'x = "ab"'
        redacted = _redact_line(line)
        # Short strings have no middle to redact
        assert isinstance(redacted, str)
