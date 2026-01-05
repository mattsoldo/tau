"""
Unit tests for GitHub client service.

Tests version parsing, checksum extraction, and release handling.
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from tau.services.github_client import (
    GitHubClient,
    GitHubRelease,
    GitHubAPIError,
    RateLimitError,
)


class TestVersionParsing:
    """Tests for version parsing from tag names."""

    @pytest.fixture
    def client(self):
        return GitHubClient(repo="owner/repo")

    def test_parse_version_with_v_prefix(self, client):
        """Version with 'v' prefix should be stripped."""
        assert client._parse_version("v1.2.3") == "1.2.3"

    def test_parse_version_without_v_prefix(self, client):
        """Version without 'v' prefix should be unchanged."""
        assert client._parse_version("1.2.3") == "1.2.3"

    def test_parse_version_prerelease(self, client):
        """Pre-release versions should be handled."""
        assert client._parse_version("v1.2.3-beta.1") == "1.2.3-beta.1"
        assert client._parse_version("v2.0.0-rc.1") == "2.0.0-rc.1"

    def test_parse_version_with_multiple_v(self, client):
        """Only leading 'v' should be stripped."""
        assert client._parse_version("vvv1.0.0") == "1.0.0"


class TestChecksumExtraction:
    """Tests for checksum extraction from release notes."""

    @pytest.fixture
    def client(self):
        return GitHubClient(repo="owner/repo")

    def test_extract_sha256_with_label(self, client):
        """Extract checksum with 'SHA256:' label."""
        notes = "Some release notes\nSHA256: abcd1234567890abcd1234567890abcd1234567890abcd1234567890abcd1234\nMore notes"
        checksum = client._extract_checksum_from_notes(notes, "test.deb")
        assert checksum == "abcd1234567890abcd1234567890abcd1234567890abcd1234567890abcd1234"

    def test_extract_sha256_lowercase_label(self, client):
        """Extract checksum with lowercase 'sha256:' label."""
        notes = "sha256: ABCD1234567890abcd1234567890abcd1234567890abcd1234567890abcd1234"
        checksum = client._extract_checksum_from_notes(notes, "test.deb")
        assert checksum == "abcd1234567890abcd1234567890abcd1234567890abcd1234567890abcd1234"

    def test_extract_checksum_file_format(self, client):
        """Extract checksum in standard checksums file format."""
        notes = "Checksums:\nabcd1234567890abcd1234567890abcd1234567890abcd1234567890abcd1234  tau-lighting_1.0.0_arm64.deb"
        checksum = client._extract_checksum_from_notes(notes, "tau-lighting_1.0.0_arm64.deb")
        assert checksum == "abcd1234567890abcd1234567890abcd1234567890abcd1234567890abcd1234"

    def test_extract_checksum_asset_name_format(self, client):
        """Extract checksum with asset name prefix."""
        notes = "tau-lighting.deb: abcd1234567890abcd1234567890abcd1234567890abcd1234567890abcd1234"
        checksum = client._extract_checksum_from_notes(notes, "tau-lighting.deb")
        assert checksum == "abcd1234567890abcd1234567890abcd1234567890abcd1234567890abcd1234"

    def test_extract_no_checksum(self, client):
        """Return None when no checksum found."""
        notes = "Just some release notes without checksums"
        checksum = client._extract_checksum_from_notes(notes, "test.deb")
        assert checksum is None

    def test_extract_checksum_empty_notes(self, client):
        """Return None for empty release notes."""
        assert client._extract_checksum_from_notes("", "test.deb") is None
        assert client._extract_checksum_from_notes(None, "test.deb") is None


class TestGitHubClientHeaders:
    """Tests for HTTP headers generation."""

    def test_headers_without_token(self):
        """Headers without authentication token."""
        client = GitHubClient(repo="owner/repo")
        headers = client.headers
        assert "Accept" in headers
        assert "X-GitHub-Api-Version" in headers
        assert "User-Agent" in headers
        assert "Authorization" not in headers

    def test_headers_with_token(self):
        """Headers with authentication token."""
        client = GitHubClient(repo="owner/repo", token="test_token")
        headers = client.headers
        assert headers["Authorization"] == "Bearer test_token"


class TestReleaseFiltering:
    """Tests for release list filtering logic."""

    @pytest.mark.asyncio
    async def test_get_releases_filters_drafts(self):
        """Draft releases should be filtered out."""
        client = GitHubClient(repo="owner/repo")

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "tag_name": "v1.0.0",
                "name": "Release 1.0.0",
                "published_at": "2026-01-01T00:00:00Z",
                "body": "Release notes",
                "prerelease": False,
                "draft": True,  # Should be filtered
                "assets": [],
            },
            {
                "tag_name": "v0.9.0",
                "name": "Release 0.9.0",
                "published_at": "2025-12-01T00:00:00Z",
                "body": "Release notes",
                "prerelease": False,
                "draft": False,
                "assets": [],
            },
        ]

        with patch.object(client, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            releases = await client.get_releases()

        assert len(releases) == 1
        assert releases[0].version == "0.9.0"

    @pytest.mark.asyncio
    async def test_get_releases_filters_prereleases_by_default(self):
        """Pre-releases should be filtered by default."""
        client = GitHubClient(repo="owner/repo")

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "tag_name": "v1.0.0-beta.1",
                "name": "Release 1.0.0 Beta",
                "published_at": "2026-01-01T00:00:00Z",
                "body": "",
                "prerelease": True,
                "draft": False,
                "assets": [],
            },
            {
                "tag_name": "v0.9.0",
                "name": "Release 0.9.0",
                "published_at": "2025-12-01T00:00:00Z",
                "body": "",
                "prerelease": False,
                "draft": False,
                "assets": [],
            },
        ]

        with patch.object(client, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            releases = await client.get_releases(include_prereleases=False)

        assert len(releases) == 1
        assert releases[0].version == "0.9.0"

    @pytest.mark.asyncio
    async def test_get_releases_includes_prereleases_when_requested(self):
        """Pre-releases should be included when requested."""
        client = GitHubClient(repo="owner/repo")

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "tag_name": "v1.0.0-beta.1",
                "name": "Release 1.0.0 Beta",
                "published_at": "2026-01-01T00:00:00Z",
                "body": "",
                "prerelease": True,
                "draft": False,
                "assets": [],
            },
            {
                "tag_name": "v0.9.0",
                "name": "Release 0.9.0",
                "published_at": "2025-12-01T00:00:00Z",
                "body": "",
                "prerelease": False,
                "draft": False,
                "assets": [],
            },
        ]

        with patch.object(client, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            releases = await client.get_releases(include_prereleases=True)

        assert len(releases) == 2


class TestAssetSelection:
    """Tests for release asset selection logic."""

    @pytest.mark.asyncio
    async def test_prefers_arm_deb_packages(self):
        """ARM .deb packages should be preferred."""
        client = GitHubClient(repo="owner/repo")

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "tag_name": "v1.0.0",
                "name": "Release 1.0.0",
                "published_at": "2026-01-01T00:00:00Z",
                "body": "",
                "prerelease": False,
                "draft": False,
                "assets": [
                    {
                        "name": "tau-lighting_1.0.0_amd64.deb",
                        "browser_download_url": "https://example.com/amd64.deb",
                        "size": 1000000,
                    },
                    {
                        "name": "tau-lighting_1.0.0_arm64.deb",
                        "browser_download_url": "https://example.com/arm64.deb",
                        "size": 900000,
                    },
                ],
            }
        ]

        with patch.object(client, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            releases = await client.get_releases()

        assert len(releases) == 1
        assert releases[0].asset_name == "tau-lighting_1.0.0_arm64.deb"
        assert releases[0].asset_url == "https://example.com/arm64.deb"

    @pytest.mark.asyncio
    async def test_falls_back_to_any_deb(self):
        """Falls back to any .deb if no ARM package."""
        client = GitHubClient(repo="owner/repo")

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "tag_name": "v1.0.0",
                "name": "Release 1.0.0",
                "published_at": "2026-01-01T00:00:00Z",
                "body": "",
                "prerelease": False,
                "draft": False,
                "assets": [
                    {
                        "name": "tau-lighting_1.0.0.deb",
                        "browser_download_url": "https://example.com/generic.deb",
                        "size": 1000000,
                    },
                    {
                        "name": "tau-lighting_1.0.0.tar.gz",
                        "browser_download_url": "https://example.com/source.tar.gz",
                        "size": 500000,
                    },
                ],
            }
        ]

        with patch.object(client, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            releases = await client.get_releases()

        assert releases[0].asset_name == "tau-lighting_1.0.0.deb"


class TestRateLimitHandling:
    """Tests for rate limit error handling."""

    @pytest.mark.asyncio
    async def test_rate_limit_error_raised(self):
        """RateLimitError should be raised when rate limited."""
        client = GitHubClient(repo="owner/repo")

        # Create mock response that simulates rate limiting
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.headers = {
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": "1735689600",  # Some future timestamp
        }
        # Make raise_for_status a no-op since we handle 403 before it
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.request.return_value = mock_response
        mock_http_client.is_closed = False
        client._client = mock_http_client

        with pytest.raises(RateLimitError) as exc_info:
            await client._make_request("GET", "https://api.github.com/test")

        assert exc_info.value.reset_at is not None
