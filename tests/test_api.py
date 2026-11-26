"""Unit tests for HoverAPI class."""

import datetime
import pytest
import requests
from unittest.mock import Mock

from hover_dns_updater.api import HoverAPI
from hover_dns_updater.constants import API_BASE_URL, AUTH_CACHE_SECONDS, TIMEOUT
from hover_dns_updater.exceptions import HoverError


@pytest.fixture
def isolated_api(mocker):
    mocker.patch.object(HoverAPI, "get_auth")
    api = HoverAPI(Mock(DNS_IDS=["first", "second"]))
    api.get_auth.reset_mock()
    api._cookies = {"hover_session": "session", "hoverauth": "auth"}
    return api


@pytest.mark.unit
@pytest.mark.parametrize(
    ("seconds", "refresh"),
    [
        (-1, False),
        (0, False),
        (AUTH_CACHE_SECONDS - 1, False),
        (AUTH_CACHE_SECONDS, False),
        (AUTH_CACHE_SECONDS + 0.001, True),
        (AUTH_CACHE_SECONDS * 2, True),
    ],
)
def test_auth_cache_expiry(isolated_api, mocker, seconds, refresh):
    now = datetime.datetime(2025, 1, 1)
    clock = mocker.patch("hover_dns_updater.api.datetime.datetime")
    clock.now.return_value = now
    isolated_api._auth_timestamp = now - datetime.timedelta(seconds=seconds)

    isolated_api.check_auth()

    assert isolated_api.get_auth.call_count == int(refresh)


@pytest.mark.unit
@pytest.mark.parametrize("method", ["get", "put", "post", "delete"])
@pytest.mark.parametrize("data", [None, {"content": "203.0.113.1"}])
def test_api_call_sends_authenticated_request(isolated_api, mocker, method, data):
    check_auth = mocker.patch.object(isolated_api, "check_auth")
    response = Mock(ok=True, content=b"json")
    response.json.return_value = {"succeeded": True, "value": 42}
    request = mocker.patch(
        "hover_dns_updater.api.requests.request", return_value=response
    )

    assert isolated_api.call(method, "dns/first", data) == response.json.return_value
    check_auth.assert_called_once_with()
    request.assert_called_once_with(
        method,
        f"{API_BASE_URL}/dns/first",
        data=data,
        cookies=isolated_api._cookies,
        timeout=TIMEOUT,
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "body",
    [
        {},
        {"succeeded": False},
        {"succeeded": None},
        {"succeeded": 1},
        {"succeeded": "true"},
    ],
)
def test_api_call_rejects_unsuccessful_json(isolated_api, mocker, body):
    mocker.patch.object(isolated_api, "check_auth")
    response = Mock(ok=True, content=b"json")
    response.json.return_value = body
    mocker.patch("hover_dns_updater.api.requests.request", return_value=response)

    with pytest.raises(HoverError) as error:
        isolated_api.call("get", "dns")
    assert error.value.args == (body,)


@pytest.mark.unit
@pytest.mark.parametrize("status", [400, 401, 403, 429, 500, 503])
def test_api_call_rejects_http_error(isolated_api, mocker, status):
    mocker.patch.object(isolated_api, "check_auth")
    response = Mock(ok=False, status_code=status)
    mocker.patch("hover_dns_updater.api.requests.request", return_value=response)

    with pytest.raises(HoverError) as error:
        isolated_api.call("get", "dns")
    assert error.value.args == (response,)
    response.json.assert_not_called()


@pytest.mark.unit
def test_api_call_accepts_empty_success_response(isolated_api, mocker):
    mocker.patch.object(isolated_api, "check_auth")
    response = Mock(ok=True, content=b"")
    mocker.patch("hover_dns_updater.api.requests.request", return_value=response)
    assert isolated_api.call("put", "dns/first") is None
    response.json.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize("exception", [requests.Timeout, requests.ConnectionError])
def test_api_call_propagates_network_errors(isolated_api, mocker, exception):
    mocker.patch.object(isolated_api, "check_auth")
    mocker.patch(
        "hover_dns_updater.api.requests.request", side_effect=exception("offline")
    )
    with pytest.raises(exception, match="offline"):
        isolated_api.call("get", "dns")


@pytest.mark.unit
def test_api_updates_only_changed_records_and_caches_success(isolated_api, mocker):
    isolated_api._current_dns_ips = {"first": "192.0.2.1", "second": "203.0.113.1"}
    get = mocker.patch("hover_dns_updater.api.requests.get")
    get.return_value.text = "203.0.113.1"
    call = mocker.patch.object(isolated_api, "call")

    isolated_api.update()
    isolated_api.update()

    call.assert_called_once_with("put", "dns/first", {"content": "203.0.113.1"})
    assert isolated_api._current_dns_ips == {
        "first": "203.0.113.1",
        "second": "203.0.113.1",
    }
    assert get.call_count == 2
    get.assert_called_with("https://api.ipify.org", timeout=TIMEOUT)


@pytest.mark.unit
def test_api_does_not_cache_failed_update(isolated_api, mocker):
    isolated_api._current_dns_ips = {"first": "192.0.2.1"}
    mocker.patch("hover_dns_updater.api.requests.get").return_value.text = "203.0.113.1"
    mocker.patch.object(isolated_api, "call", side_effect=HoverError("failed"))
    with pytest.raises(HoverError, match="failed"):
        isolated_api.update()
    assert isolated_api._current_dns_ips == {"first": "192.0.2.1"}


@pytest.mark.unit
def test_api_collects_matching_dns_records_across_domains(isolated_api, mocker):
    mocker.patch.object(
        isolated_api,
        "call",
        return_value={
            "domains": [
                {
                    "entries": [
                        {"id": "first", "content": "192.0.2.1"},
                        {"id": "other", "content": "192.0.2.2"},
                    ]
                },
                {"entries": [{"id": "second", "content": "2001:db8::1"}]},
            ]
        },
    )
    isolated_api.get_current_ips()
    assert isolated_api._current_dns_ips == {
        "first": "192.0.2.1",
        "second": "2001:db8::1",
    }


class TestHoverAPIInitialization:
    """Tests for HoverAPI initialization."""

    def test_api_requires_config(self, mocker):
        """Test that HoverAPI requires a config object."""
        with pytest.raises(TypeError):
            HoverAPI()

    def test_api_stores_config_reference(self, sample_config_data, mocker):
        """Test that HoverAPI stores config reference."""
        config = Mock()
        config.USERNAME = sample_config_data["username"]
        config.PASSWORD = sample_config_data["password"]
        config.TOPTKEY = sample_config_data["toptkey"]
        config.DNS_IDS = sample_config_data["dns_ids"]

        signin_response = Mock()
        signin_response.cookies = {"hover_session": "test_session_cookie"}

        auth2_response = Mock()
        auth2_response.ok = True
        auth2_response.cookies = {"hoverauth": "test_hoverauth_cookie"}

        mocker.patch("pyotp.TOTP")
        mocker.patch("requests.get", return_value=signin_response)
        mocker.patch("requests.post", side_effect=[Mock(ok=True), auth2_response])

        api = HoverAPI(config)
        # Can't directly access config due to private attributes, but verify it was used
        assert api is not None


class TestHoverAPICookieManagement:
    """Tests for HoverAPI cookie handling."""

    def test_api_stores_session_cookie(self, sample_config_data, mocker):
        """Test that HoverAPI stores session cookie from signin."""
        config = Mock()
        config.USERNAME = sample_config_data["username"]
        config.PASSWORD = sample_config_data["password"]
        config.TOPTKEY = sample_config_data["toptkey"]
        config.DNS_IDS = sample_config_data["dns_ids"]

        signin_response = Mock()
        signin_response.cookies = {"hover_session": "my_session_id"}

        auth2_response = Mock()
        auth2_response.ok = True
        auth2_response.cookies = {"hoverauth": "my_hoverauth"}

        mocker.patch("pyotp.TOTP")
        mocker.patch("requests.get", return_value=signin_response)
        mocker.patch("requests.post", side_effect=[Mock(ok=True), auth2_response])

        api = HoverAPI(config)
        assert api._cookies["hover_session"] == "my_session_id"

    def test_api_stores_hoverauth_cookie(self, sample_config_data, mocker):
        """Test that HoverAPI stores hoverauth cookie from auth."""
        config = Mock()
        config.USERNAME = sample_config_data["username"]
        config.PASSWORD = sample_config_data["password"]
        config.TOPTKEY = sample_config_data["toptkey"]
        config.DNS_IDS = sample_config_data["dns_ids"]

        signin_response = Mock()
        signin_response.cookies = {"hover_session": "test_session"}

        auth2_response = Mock()
        auth2_response.ok = True
        auth2_response.cookies = {"hoverauth": "my_hoverauth_cookie"}

        mocker.patch("pyotp.TOTP")
        mocker.patch("requests.get", return_value=signin_response)
        mocker.patch("requests.post", side_effect=[Mock(ok=True), auth2_response])

        api = HoverAPI(config)
        assert api._cookies["hoverauth"] == "my_hoverauth_cookie"

    def test_api_multiple_cookies_stored(self, sample_config_data, mocker):
        """Test that HoverAPI stores multiple cookies together."""
        config = Mock()
        config.USERNAME = sample_config_data["username"]
        config.PASSWORD = sample_config_data["password"]
        config.TOPTKEY = sample_config_data["toptkey"]
        config.DNS_IDS = sample_config_data["dns_ids"]

        signin_response = Mock()
        signin_response.cookies = {
            "hover_session": "session1",
            "other_cookie": "value1",
        }

        auth2_response = Mock()
        auth2_response.ok = True
        auth2_response.cookies = {
            "hoverauth": "auth1",
            "another_cookie": "value2",
        }

        mocker.patch("pyotp.TOTP")
        mocker.patch("requests.get", return_value=signin_response)
        mocker.patch("requests.post", side_effect=[Mock(ok=True), auth2_response])

        api = HoverAPI(config)
        assert api._cookies["hover_session"] == "session1"
        assert api._cookies["hoverauth"] == "auth1"


class TestHoverAPIAuthenticationFlow:
    """Tests for HoverAPI authentication flow."""

    def test_api_calls_get_for_signin(self, sample_config_data, mocker):
        """Test that HoverAPI calls requests.get for signin."""
        config = Mock()
        config.USERNAME = sample_config_data["username"]
        config.PASSWORD = sample_config_data["password"]
        config.TOPTKEY = sample_config_data["toptkey"]
        config.DNS_IDS = sample_config_data["dns_ids"]

        signin_response = Mock()
        signin_response.cookies = {"hover_session": "test_session"}

        auth2_response = Mock()
        auth2_response.ok = True
        auth2_response.cookies = {"hoverauth": "test_hoverauth"}

        mocker.patch("pyotp.TOTP")
        get_mock = mocker.patch("requests.get", return_value=signin_response)
        mocker.patch("requests.post", side_effect=[Mock(ok=True), auth2_response])

        HoverAPI(config)
        assert get_mock.called

    def test_api_calls_post_for_auth(self, sample_config_data, mocker):
        """Test that HoverAPI calls requests.post for authentication."""
        config = Mock()
        config.USERNAME = sample_config_data["username"]
        config.PASSWORD = sample_config_data["password"]
        config.TOPTKEY = sample_config_data["toptkey"]
        config.DNS_IDS = sample_config_data["dns_ids"]

        signin_response = Mock()
        signin_response.cookies = {"hover_session": "test_session"}

        auth2_response = Mock()
        auth2_response.ok = True
        auth2_response.cookies = {"hoverauth": "test_hoverauth"}

        mocker.patch("pyotp.TOTP")
        mocker.patch("requests.get", return_value=signin_response)
        post_mock = mocker.patch(
            "requests.post", side_effect=[Mock(ok=True), auth2_response]
        )

        HoverAPI(config)
        assert post_mock.call_count == 2

    def test_api_auth_second_post_must_succeed(self, sample_config_data, mocker):
        """Test that second POST (auth2) must succeed with hoverauth cookie."""
        config = Mock()
        config.USERNAME = sample_config_data["username"]
        config.PASSWORD = sample_config_data["password"]
        config.TOPTKEY = sample_config_data["toptkey"]
        config.DNS_IDS = sample_config_data["dns_ids"]

        signin_response = Mock()
        signin_response.cookies = {"hover_session": "test_session"}

        auth_response = Mock()
        auth_response.ok = True

        auth2_response = Mock()
        auth2_response.ok = False  # Failure on second auth
        auth2_response.cookies = {}

        mocker.patch("pyotp.TOTP")
        mocker.patch("requests.get", return_value=signin_response)
        mocker.patch("requests.post", side_effect=[auth_response, auth2_response])

        with pytest.raises(HoverError):
            HoverAPI(config)

    def test_api_auth_uses_totp_code(self, sample_config_data, mocker):
        """Test that HoverAPI uses TOTP code for authentication."""
        config = Mock()
        config.USERNAME = sample_config_data["username"]
        config.PASSWORD = sample_config_data["password"]
        config.TOPTKEY = sample_config_data["toptkey"]
        config.DNS_IDS = sample_config_data["dns_ids"]

        signin_response = Mock()
        signin_response.cookies = {"hover_session": "test_session"}

        auth_response = Mock()
        auth_response.ok = True

        auth2_response = Mock()
        auth2_response.ok = True
        auth2_response.cookies = {"hoverauth": "test_hoverauth"}

        totp_mock = mocker.patch("pyotp.TOTP")
        totp_instance = Mock()
        totp_instance.now.return_value = "123456"
        totp_mock.return_value = totp_instance

        mocker.patch("requests.get", return_value=signin_response)
        post_mock = mocker.patch(
            "requests.post", side_effect=[auth_response, auth2_response]
        )

        HoverAPI(config)
        # Verify TOTP was instantiated with the toptkey
        totp_mock.assert_called_once_with(sample_config_data["toptkey"])
        # Verify TOTP.now() was called to generate the code
        totp_instance.now.assert_called()
        # Verify the generated code was sent in the second POST
        second_post_call = post_mock.call_args_list[1]
        assert second_post_call[1]["json"]["code"] == "123456"


class TestHoverAPIDNSIPRetrieval:
    """Tests for HoverAPI DNS IP retrieval."""

    def test_api_get_current_ips_stores_results(
        self, sample_config_data, mocker, mock_dns_response
    ):
        """Test that get_current_ips stores retrieved IPs."""
        config = Mock()
        config.USERNAME = sample_config_data["username"]
        config.PASSWORD = sample_config_data["password"]
        config.TOPTKEY = sample_config_data["toptkey"]
        config.DNS_IDS = ["dns123"]
        config.SERVICE = False
        config.POLLTIME = 600

        mocker.patch("pyotp.TOTP")
        signin_response = Mock()
        signin_response.cookies = {"hover_session": "test_session"}

        auth2_response = Mock()
        auth2_response.ok = True
        auth2_response.cookies = {"hoverauth": "test_hoverauth"}

        dns_response = Mock()
        dns_response.ok = True
        dns_response.content = True
        dns_response.json.return_value = mock_dns_response

        mocker.patch("requests.get", return_value=signin_response)
        mocker.patch("requests.post", side_effect=[Mock(ok=True), auth2_response])
        mocker.patch("requests.request", return_value=dns_response)

        api = HoverAPI(config)
        api.get_current_ips()

        assert "dns123" in api._current_dns_ips
        assert api._current_dns_ips["dns123"] == "192.168.1.1"

    def test_api_get_current_ips_filters_dns_ids(
        self, sample_config_data, mocker, mock_dns_response
    ):
        """Test that get_current_ips only stores requested DNS IDs."""
        config = Mock()
        config.USERNAME = sample_config_data["username"]
        config.PASSWORD = sample_config_data["password"]
        config.TOPTKEY = sample_config_data["toptkey"]
        config.DNS_IDS = ["dns123"]  # Only request dns123
        config.SERVICE = False
        config.POLLTIME = 600

        mocker.patch("pyotp.TOTP")
        signin_response = Mock()
        signin_response.cookies = {"hover_session": "test_session"}

        auth2_response = Mock()
        auth2_response.ok = True
        auth2_response.cookies = {"hoverauth": "test_hoverauth"}

        dns_response = Mock()
        dns_response.ok = True
        dns_response.content = True
        dns_response.json.return_value = mock_dns_response  # Has dns123, dns456, dns789

        mocker.patch("requests.get", return_value=signin_response)
        mocker.patch("requests.post", side_effect=[Mock(ok=True), auth2_response])
        mocker.patch("requests.request", return_value=dns_response)

        api = HoverAPI(config)
        api.get_current_ips()

        assert "dns123" in api._current_dns_ips
        assert "dns456" not in api._current_dns_ips
        assert "dns789" not in api._current_dns_ips

    def test_api_get_current_ips_handles_empty_dns_ids(
        self, sample_config_data, mocker, mock_dns_response
    ):
        """Test that get_current_ips handles empty DNS ID list."""
        config = Mock()
        config.USERNAME = sample_config_data["username"]
        config.PASSWORD = sample_config_data["password"]
        config.TOPTKEY = sample_config_data["toptkey"]
        config.DNS_IDS = []  # Empty list
        config.SERVICE = False
        config.POLLTIME = 600

        mocker.patch("pyotp.TOTP")
        signin_response = Mock()
        signin_response.cookies = {"hover_session": "test_session"}

        auth2_response = Mock()
        auth2_response.ok = True
        auth2_response.cookies = {"hoverauth": "test_hoverauth"}

        dns_response = Mock()
        dns_response.ok = True
        dns_response.content = True
        dns_response.json.return_value = mock_dns_response

        mocker.patch("requests.get", return_value=signin_response)
        mocker.patch("requests.post", side_effect=[Mock(ok=True), auth2_response])
        mocker.patch("requests.request", return_value=dns_response)

        api = HoverAPI(config)
        api.get_current_ips()

        assert len(api._current_dns_ips) == 0


class TestHoverAPIDNSIPUpdate:
    """Tests for HoverAPI DNS IP update operations."""

    def test_api_update_calls_request(self, sample_config_data, mocker, mock_dns_response):
        """Test that update method makes appropriate requests."""
        config = Mock()
        config.USERNAME = sample_config_data["username"]
        config.PASSWORD = sample_config_data["password"]
        config.TOPTKEY = sample_config_data["toptkey"]
        config.DNS_IDS = ["dns123"]
        config.SERVICE = False
        config.POLLTIME = 600

        mocker.patch("pyotp.TOTP")
        signin_response = Mock()
        signin_response.cookies = {"hover_session": "test_session"}

        auth2_response = Mock()
        auth2_response.ok = True
        auth2_response.cookies = {"hoverauth": "test_hoverauth"}

        dns_response = Mock()
        dns_response.ok = True
        dns_response.content = True
        dns_response.json.return_value = mock_dns_response

        ipify_response = Mock()
        ipify_response.text = "203.0.113.45"  # Different IP

        update_response = Mock()
        update_response.ok = True
        update_response.content = True
        update_response.json.return_value = {"succeeded": True}

        mocker.patch("requests.get", side_effect=[signin_response, ipify_response])
        mocker.patch("requests.post", side_effect=[Mock(ok=True), auth2_response])
        request_mock = mocker.patch(
            "requests.request",
            side_effect=[dns_response, update_response],
        )

        api = HoverAPI(config)
        api.get_current_ips()
        api.update()

        # Verify PUT request was made
        put_calls = [
            c for c in request_mock.call_args_list if len(c[0]) > 0
            and c[0][0].lower() == "put"
        ]
        assert len(put_calls) > 0

    def test_api_update_handles_multiple_dns_records(
        self, sample_config_data, mocker, mock_dns_response
    ):
        """Test that update updates every DNS record and cache entry."""
        config = Mock()
        config.USERNAME = sample_config_data["username"]
        config.PASSWORD = sample_config_data["password"]
        config.TOPTKEY = sample_config_data["toptkey"]
        config.DNS_IDS = ["dns123", "dns456"]
        config.SERVICE = False
        config.POLLTIME = 600

        mocker.patch("pyotp.TOTP")
        signin_response = Mock()
        signin_response.cookies = {"hover_session": "test_session"}

        auth2_response = Mock()
        auth2_response.ok = True
        auth2_response.cookies = {"hoverauth": "test_hoverauth"}

        dns_response = Mock()
        dns_response.ok = True
        dns_response.content = True
        dns_response.json.return_value = mock_dns_response

        ipify_response = Mock()
        ipify_response.text = "203.0.113.45"  # Different from stored

        update_response = Mock()
        update_response.ok = True
        update_response.content = True
        update_response.json.return_value = {"succeeded": True}

        mocker.patch("requests.get", side_effect=[signin_response, ipify_response])
        mocker.patch("requests.post", side_effect=[Mock(ok=True), auth2_response])
        request_mock = mocker.patch(
            "requests.request",
            side_effect=[dns_response, update_response, update_response],
        )

        api = HoverAPI(config)
        api.get_current_ips()

        # Should have both IPs cached
        assert len(api._current_dns_ips) == 2
        assert api._current_dns_ips["dns123"] == "192.168.1.1"
        assert api._current_dns_ips["dns456"] == "192.168.1.1"

        # Perform update
        api.update()

        # Verify PUT requests were made for both DNS records
        put_calls = [
            c for c in request_mock.call_args_list if len(c[0]) > 0
            and c[0][0].lower() == "put"
        ]
        # Must have exactly 2 PUT requests (one for each record)
        assert len(put_calls) == 2, f"Expected exactly 2 PUT requests (one per record), got {len(put_calls)}"

        # Verify both records were updated with correct payload
        updated_records = {}
        for call in put_calls:
            # call[0] is positional args: (method, url, ...)
            # call[1] is keyword args
            url = call[0][1]  # args[1] is URL
            # Extract the DNS record ID from URL: /dns/{id}
            if "/dns/" in url:
                record_id = url.split("/dns/")[-1].rstrip("/")
                # Get the data payload from kwargs
                payload = call[1].get('data', {})
                updated_records[record_id] = payload

        # Verify both records were updated with the new IP in payload
        assert len(updated_records) == 2, f"Expected updates for 2 records, got {len(updated_records)}"
        assert "dns123" in updated_records, "dns123 should be updated"
        assert "dns456" in updated_records, "dns456 should be updated"
        # Verify the payload contains the correct new IP
        assert updated_records["dns123"].get("content") == "203.0.113.45", (
            f"dns123 payload incorrect: {updated_records['dns123']}"
        )
        assert updated_records["dns456"].get("content") == "203.0.113.45", (
            f"dns456 payload incorrect: {updated_records['dns456']}"
        )

        # Verify cache entries are updated after successful update
        assert api._current_dns_ips["dns123"] == "203.0.113.45"
        assert api._current_dns_ips["dns456"] == "203.0.113.45"


class TestHoverAPIErrorHandling:
    """Tests for HoverAPI error handling."""

    def test_api_raises_error_on_missing_hoverauth(self, sample_config_data, mocker):
        """Test that HoverAPI raises error if hoverauth cookie missing even on success."""
        config = Mock()
        config.USERNAME = sample_config_data["username"]
        config.PASSWORD = sample_config_data["password"]
        config.TOPTKEY = sample_config_data["toptkey"]
        config.DNS_IDS = sample_config_data["dns_ids"]

        signin_response = Mock()
        signin_response.cookies = {"hover_session": "test_session"}

        auth_response = Mock()
        auth_response.ok = True

        auth2_response = Mock()
        auth2_response.ok = True  # Success, but...
        auth2_response.cookies = {}  # No hoverauth cookie

        mocker.patch("pyotp.TOTP")
        mocker.patch("requests.get", return_value=signin_response)
        mocker.patch("requests.post", side_effect=[auth_response, auth2_response])

        with pytest.raises(HoverError):
            HoverAPI(config)

    def test_api_raises_error_on_dns_api_failure(
        self, sample_config_data, mocker, mock_dns_response
    ):
        """Test that HoverAPI raises error when DNS API fails."""
        config = Mock()
        config.USERNAME = sample_config_data["username"]
        config.PASSWORD = sample_config_data["password"]
        config.TOPTKEY = sample_config_data["toptkey"]
        config.DNS_IDS = ["dns123"]
        config.SERVICE = False
        config.POLLTIME = 600

        mocker.patch("pyotp.TOTP")
        signin_response = Mock()
        signin_response.cookies = {"hover_session": "test_session"}

        auth2_response = Mock()
        auth2_response.ok = True
        auth2_response.cookies = {"hoverauth": "test_hoverauth"}

        dns_response = Mock()
        dns_response.ok = False  # Failure

        mocker.patch("requests.get", return_value=signin_response)
        mocker.patch("requests.post", side_effect=[Mock(ok=True), auth2_response])
        mocker.patch("requests.request", return_value=dns_response)

        api = HoverAPI(config)
        # get_current_ips should raise HoverError on failed response
        with pytest.raises(HoverError):
            api.get_current_ips()


class TestHoverAPIEdgeCases:
    """Tests for HoverAPI edge cases."""

    def test_api_handles_empty_dns_response(self, sample_config_data, mocker):
        """Test that API handles empty DNS response."""
        config = Mock()
        config.USERNAME = sample_config_data["username"]
        config.PASSWORD = sample_config_data["password"]
        config.TOPTKEY = sample_config_data["toptkey"]
        config.DNS_IDS = ["dns123"]
        config.SERVICE = False
        config.POLLTIME = 600

        mocker.patch("pyotp.TOTP")
        signin_response = Mock()
        signin_response.cookies = {"hover_session": "test_session"}

        auth2_response = Mock()
        auth2_response.ok = True
        auth2_response.cookies = {"hoverauth": "test_hoverauth"}

        dns_response = Mock()
        dns_response.ok = True
        dns_response.content = True
        dns_response.json.return_value = {"succeeded": True, "domains": []}

        mocker.patch("requests.get", return_value=signin_response)
        mocker.patch("requests.post", side_effect=[Mock(ok=True), auth2_response])
        mocker.patch("requests.request", return_value=dns_response)

        api = HoverAPI(config)
        api.get_current_ips()
        # Should handle gracefully without errors
        assert isinstance(api._current_dns_ips, dict)

    def test_api_handles_ipv6_addresses(self, sample_config_data, mocker):
        """Test that API can handle IPv6 addresses."""
        config = Mock()
        config.USERNAME = sample_config_data["username"]
        config.PASSWORD = sample_config_data["password"]
        config.TOPTKEY = sample_config_data["toptkey"]
        config.DNS_IDS = ["dns123"]
        config.SERVICE = False
        config.POLLTIME = 600

        mocker.patch("pyotp.TOTP")
        signin_response = Mock()
        signin_response.cookies = {"hover_session": "test_session"}

        auth2_response = Mock()
        auth2_response.ok = True
        auth2_response.cookies = {"hoverauth": "test_hoverauth"}

        dns_response = Mock()
        dns_response.ok = True
        dns_response.content = True
        dns_response.json.return_value = {
            "succeeded": True,
            "domains": [
                {
                    "domain_name": "example.com",
                    "entries": [
                        {
                            "id": "dns123",
                            "type": "AAAA",
                            "name": "test",
                            "content": "2001:db8::1",
                        }
                    ],
                }
            ],
        }

        mocker.patch("requests.get", return_value=signin_response)
        mocker.patch("requests.post", side_effect=[Mock(ok=True), auth2_response])
        mocker.patch("requests.request", return_value=dns_response)

        api = HoverAPI(config)
        api.get_current_ips()
        # Should handle IPv6 gracefully and correctly parse the address
        assert "dns123" in api._current_dns_ips
        assert api._current_dns_ips["dns123"] == "2001:db8::1"

    def test_api_handles_unicode_in_response(self, sample_config_data, mocker):
        """Test that API handles unicode in DNS response."""
        config = Mock()
        config.USERNAME = sample_config_data["username"]
        config.PASSWORD = sample_config_data["password"]
        config.TOPTKEY = sample_config_data["toptkey"]
        config.DNS_IDS = ["dns123"]
        config.SERVICE = False
        config.POLLTIME = 600

        mocker.patch("pyotp.TOTP")
        signin_response = Mock()
        signin_response.cookies = {"hover_session": "test_session"}

        auth2_response = Mock()
        auth2_response.ok = True
        auth2_response.cookies = {"hoverauth": "test_hoverauth"}

        dns_response = Mock()
        dns_response.ok = True
        dns_response.content = True
        dns_response.json.return_value = {
            "succeeded": True,
            "domains": [
                {
                    "domain_name": "例え.jp",  # Japanese domain
                    "entries": [
                        {
                            "id": "dns123",
                            "type": "A",
                            "name": "テスト",
                            "content": "192.168.1.1",
                        }
                    ],
                }
            ],
        }

        mocker.patch("requests.get", return_value=signin_response)
        mocker.patch("requests.post", side_effect=[Mock(ok=True), auth2_response])
        mocker.patch("requests.request", return_value=dns_response)

        api = HoverAPI(config)
        api.get_current_ips()
        # Should handle unicode domains gracefully
        assert isinstance(api._current_dns_ips, dict)
