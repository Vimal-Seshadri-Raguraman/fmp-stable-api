# current/tests/test_fmp.py
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "publish"))


class TestRateLimiter:
    def test_can_make_request_within_limit(self):
        from fmp_stable_api.rate_limiter import RateLimiter
        rl = RateLimiter(minute_limit=10)
        assert rl.can_make_request() is True

    def test_cannot_make_request_at_limit(self):
        from fmp_stable_api.rate_limiter import RateLimiter
        rl = RateLimiter(minute_limit=2)
        rl.record_request()
        rl.record_request()
        assert rl.can_make_request() is False

    def test_get_remaining_decrements(self):
        from fmp_stable_api.rate_limiter import RateLimiter
        rl = RateLimiter(minute_limit=5)
        assert rl.get_remaining() == 5
        rl.record_request()
        assert rl.get_remaining() == 4


class TestEndpoints:
    def test_safe_param_name_passthrough(self):
        from fmp_stable_api.endpoints import safe_param_name
        assert safe_param_name("symbol") == "symbol"

    def test_safe_param_name_keyword(self):
        from fmp_stable_api.endpoints import safe_param_name
        assert safe_param_name("from") == "from_"

    def test_restore_param_names(self):
        from fmp_stable_api.endpoints import restore_param_names
        result = restore_param_names({"from_": "2024-01-01", "symbol": "AAPL"})
        assert result == {"from": "2024-01-01", "symbol": "AAPL"}

    def test_build_endpoint_func_calls_make_request(self):
        from fmp_stable_api.endpoints import build_endpoint_func
        calls = []
        def fake_make_request(path, params):
            calls.append((path, params))
            return {"ok": True}
        fn = build_endpoint_func(
            path="search-symbol",
            required_params=["symbol"],
            optional_params=["limit"],
            make_request=fake_make_request,
        )
        result = fn(symbol="AAPL", limit="10")
        assert calls == [("search-symbol", {"symbol": "AAPL", "limit": "10"})]
        assert result == {"ok": True}


class TestAPIClient:
    def test_fmp_importable(self):
        from fmp_stable_api import FMP
        assert FMP is not None

    def test_fmp_version(self):
        import fmp_stable_api
        assert fmp_stable_api.__version__ == "2.1.1"

    def test_invalid_client_type_raises(self):
        from fmp_stable_api import FMP
        with pytest.raises(ValueError, match="Invalid client_type"):
            FMP(client_type="NotAType", client_key="dummy")

    def test_enterprise_requires_custom_limit(self):
        from fmp_stable_api import FMP
        with pytest.raises(ValueError, match="requires custom_daily_limit"):
            FMP(client_type="Enterprise", client_key="dummy")

    def test_category_proxy_returned_on_getattr(self):
        from fmp_stable_api import FMP
        from fmp_stable_api.client import CategoryProxy
        client = FMP(client_type="Premium", client_key="dummy")
        # Pick a category that exists in fmp_endpoints.json
        # 'Search' is a top-level category in the bundled endpoints
        category = client.Search
        assert isinstance(category, CategoryProxy)


class TestRequestParsing:
    class _Resp:
        def __init__(self, content, headers, status=200):
            self.content = content
            self.text = content.decode("latin-1") if isinstance(content, bytes) else content
            self.headers = headers
            self.status_code = status
        def json(self):
            import json
            return json.loads(self.text)

    def _client(self, resp):
        from fmp_stable_api import FMP
        c = FMP(client_type="Premium", client_key="test")
        c._session.get = lambda url, params=None, timeout=None: resp
        return c

    def test_json_response(self):
        c = self._client(self._Resp(b'[{"a": 1}]', {"content-type": "application/json"}))
        assert c.request("https://financialmodelingprep.com/stable/x") == [{"a": 1}]

    def test_csv_response(self):
        c = self._client(self._Resp(b"a,b\n1,2", {"content-type": "text/csv"}))
        r = c.request("https://financialmodelingprep.com/stable/x")
        assert r["content_type"] == "csv" and r["csv_data"].startswith("a,b")

    def test_binary_with_json_header(self):
        body = b"PK\x03\x04not-json"
        c = self._client(self._Resp(body, {
            "content-type": "application/json; charset=utf-8",
            "content-disposition": "attachment; filename = AAPL_2022_FY_.xlsx",
        }))
        r = c.request("https://financialmodelingprep.com/stable/financial-reports-xlsx")
        assert r["binary_data"] == body
        assert r["filename"] == "AAPL_2022_FY_.xlsx"

    def test_filename_from_disposition_forms(self):
        from fmp_stable_api.client import _filename_from_disposition as f
        assert f('attachment; filename="a.xlsx"') == "a.xlsx"
        assert f("attachment; filename = b.csv") == "b.csv"
        assert f("attachment; filename*=UTF-8''c.json") == "c.json"
        assert f("inline") is None
        assert f("") is None


class TestUpdater:
    def test_load_endpoints_returns_dict(self):
        from fmp_stable_api.updater import load_endpoints
        data = load_endpoints()
        assert isinstance(data, dict)
        assert "endpoints" in data

    def test_update_endpoints_callable(self):
        from fmp_stable_api import update_endpoints
        assert callable(update_endpoints)

    def test_get_skill_returns_markdown(self):
        from fmp_stable_api import get_skill
        content = get_skill()
        assert isinstance(content, str)
        assert content.startswith("---")
        assert "# FMP" in content

    def test_client_get_skill_matches_module(self):
        from fmp_stable_api import FMP, get_skill
        client = FMP(client_type="Premium", client_key="test")
        assert client.get_skill() == get_skill()

    def test_get_skill_md_path_readable(self):
        from fmp_stable_api.updater import get_skill_md_path
        path = get_skill_md_path()
        assert os.path.exists(path)
        with open(path) as f:
            content = f.read()
        assert "fmp" in content.lower()
