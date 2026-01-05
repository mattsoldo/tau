"""
GitHub Releases Client - Fetches releases from GitHub API

Handles communication with GitHub's Releases API, including:
- Fetching available releases
- Downloading release assets
- Checksum verification
- Rate limit handling
"""
import asyncio
import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

import httpx
import structlog

logger = structlog.get_logger(__name__)

# GitHub API constants
GITHUB_API_BASE = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"
DEFAULT_TIMEOUT = 30.0
DOWNLOAD_TIMEOUT = 300.0


@dataclass
class GitHubRelease:
    """Represents a GitHub release"""

    version: str
    tag_name: str
    name: str
    published_at: datetime
    release_notes: str
    prerelease: bool
    draft: bool
    asset_url: Optional[str] = None
    asset_name: Optional[str] = None
    asset_size: Optional[int] = None
    asset_checksum: Optional[str] = None
    html_url: Optional[str] = None


class GitHubAPIError(Exception):
    """Base exception for GitHub API errors"""

    pass


class RateLimitError(GitHubAPIError):
    """Raised when GitHub API rate limit is exceeded"""

    def __init__(self, reset_at: datetime):
        self.reset_at = reset_at
        super().__init__(f"Rate limit exceeded. Resets at {reset_at}")


class GitHubClient:
    """
    Client for interacting with GitHub Releases API

    Handles fetching releases, downloading assets, and verifying checksums.
    """

    def __init__(
        self,
        repo: str,
        token: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """
        Initialize GitHub client

        Args:
            repo: Repository in "owner/repo" format
            token: Optional GitHub API token for higher rate limits
            timeout: Request timeout in seconds
        """
        self.repo = repo
        self.token = token
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def headers(self) -> Dict[str, str]:
        """Get headers for GitHub API requests"""
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": "tau-lighting-control/1.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers=self.headers,
                follow_redirects=True,
            )
        return self._client

    async def close(self):
        """Close the HTTP client"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _make_request(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> httpx.Response:
        """Make an HTTP request with error handling"""
        client = await self._get_client()

        try:
            response = await client.request(method, url, **kwargs)

            # Check for rate limiting
            if response.status_code == 403:
                remaining = response.headers.get("X-RateLimit-Remaining", "0")
                if remaining == "0":
                    reset_timestamp = int(response.headers.get("X-RateLimit-Reset", "0"))
                    reset_at = datetime.fromtimestamp(reset_timestamp)
                    raise RateLimitError(reset_at)

            response.raise_for_status()
            return response

        except httpx.HTTPStatusError as e:
            logger.error(
                "github_api_error",
                status_code=e.response.status_code,
                url=url,
                detail=e.response.text[:500] if e.response.text else None,
            )
            raise GitHubAPIError(f"GitHub API error: {e.response.status_code}") from e
        except httpx.RequestError as e:
            logger.error("github_request_error", url=url, error=str(e))
            raise GitHubAPIError(f"Request failed: {str(e)}") from e

    def _parse_version(self, tag_name: str) -> str:
        """
        Parse version from tag name

        Handles formats like "v1.2.3", "1.2.3", "v1.2.3-beta.1"
        """
        # Remove leading 'v' if present
        version = tag_name.lstrip("v")
        return version

    def _extract_checksum_from_notes(self, release_notes: str, asset_name: str) -> Optional[str]:
        """
        Extract SHA256 checksum from release notes

        Looks for patterns like:
        - "SHA256: abc123..."
        - "asset-name.deb: abc123..."
        - Lines in checksums format "abc123  asset-name.deb"
        """
        if not release_notes:
            return None

        # Pattern 1: "SHA256: <hash>" or "sha256: <hash>"
        sha_pattern = re.compile(r"sha256[:\s]+([a-fA-F0-9]{64})", re.IGNORECASE)
        match = sha_pattern.search(release_notes)
        if match:
            return match.group(1).lower()

        # Pattern 2: "<asset_name>: <hash>" or "<hash>  <asset_name>"
        asset_base = Path(asset_name).stem if asset_name else ""
        if asset_base:
            # Try "<name>: <hash>"
            asset_pattern = re.compile(
                rf"{re.escape(asset_base)}[^:]*:\s*([a-fA-F0-9]{{64}})", re.IGNORECASE
            )
            match = asset_pattern.search(release_notes)
            if match:
                return match.group(1).lower()

            # Try "<hash>  <name>" (checksums file format)
            checksums_pattern = re.compile(
                rf"([a-fA-F0-9]{{64}})\s+\S*{re.escape(asset_base)}", re.IGNORECASE
            )
            match = checksums_pattern.search(release_notes)
            if match:
                return match.group(1).lower()

        return None

    async def get_releases(
        self,
        include_prereleases: bool = False,
        per_page: int = 30,
    ) -> List[GitHubRelease]:
        """
        Fetch releases from GitHub API

        Args:
            include_prereleases: Whether to include pre-release versions
            per_page: Number of releases to fetch (max 100)

        Returns:
            List of GitHubRelease objects
        """
        url = f"{GITHUB_API_BASE}/repos/{self.repo}/releases"
        params = {"per_page": min(per_page, 100)}

        logger.info("fetching_github_releases", repo=self.repo, include_prereleases=include_prereleases)

        response = await self._make_request("GET", url, params=params)
        releases_data = response.json()

        releases = []
        for release_data in releases_data:
            # Skip drafts
            if release_data.get("draft", False):
                continue

            # Skip prereleases if not requested
            is_prerelease = release_data.get("prerelease", False)
            if is_prerelease and not include_prereleases:
                continue

            # Find the appropriate asset (look for .deb or .tar.gz)
            asset_url = None
            asset_name = None
            asset_size = None
            for asset in release_data.get("assets", []):
                name = asset.get("name", "")
                # Prefer .deb packages for Raspberry Pi
                if name.endswith(".deb") and ("arm" in name.lower() or "all" in name.lower()):
                    asset_url = asset.get("browser_download_url")
                    asset_name = name
                    asset_size = asset.get("size")
                    break
                # Fallback to any .deb
                elif name.endswith(".deb") and not asset_url:
                    asset_url = asset.get("browser_download_url")
                    asset_name = name
                    asset_size = asset.get("size")
                # Or .tar.gz as last resort
                elif name.endswith(".tar.gz") and not asset_url:
                    asset_url = asset.get("browser_download_url")
                    asset_name = name
                    asset_size = asset.get("size")

            release_notes = release_data.get("body", "") or ""
            asset_checksum = self._extract_checksum_from_notes(release_notes, asset_name)

            # Parse published date
            published_str = release_data.get("published_at", "")
            published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))

            release = GitHubRelease(
                version=self._parse_version(release_data["tag_name"]),
                tag_name=release_data["tag_name"],
                name=release_data.get("name", release_data["tag_name"]),
                published_at=published_at,
                release_notes=release_notes,
                prerelease=is_prerelease,
                draft=False,
                asset_url=asset_url,
                asset_name=asset_name,
                asset_size=asset_size,
                asset_checksum=asset_checksum,
                html_url=release_data.get("html_url"),
            )
            releases.append(release)

        logger.info("fetched_releases", count=len(releases))
        return releases

    async def get_latest_release(
        self,
        include_prereleases: bool = False,
    ) -> Optional[GitHubRelease]:
        """
        Get the latest release

        Args:
            include_prereleases: Whether to consider pre-releases

        Returns:
            Latest GitHubRelease or None if no releases found
        """
        if include_prereleases:
            # Need to fetch all and filter
            releases = await self.get_releases(include_prereleases=True, per_page=10)
            return releases[0] if releases else None

        # Use the /latest endpoint for stable releases
        url = f"{GITHUB_API_BASE}/repos/{self.repo}/releases/latest"

        try:
            response = await self._make_request("GET", url)
            release_data = response.json()

            # Find asset
            asset_url = None
            asset_name = None
            asset_size = None
            for asset in release_data.get("assets", []):
                name = asset.get("name", "")
                if name.endswith(".deb"):
                    asset_url = asset.get("browser_download_url")
                    asset_name = name
                    asset_size = asset.get("size")
                    break

            release_notes = release_data.get("body", "") or ""
            asset_checksum = self._extract_checksum_from_notes(release_notes, asset_name)

            published_str = release_data.get("published_at", "")
            published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))

            return GitHubRelease(
                version=self._parse_version(release_data["tag_name"]),
                tag_name=release_data["tag_name"],
                name=release_data.get("name", release_data["tag_name"]),
                published_at=published_at,
                release_notes=release_notes,
                prerelease=False,
                draft=False,
                asset_url=asset_url,
                asset_name=asset_name,
                asset_size=asset_size,
                asset_checksum=asset_checksum,
                html_url=release_data.get("html_url"),
            )
        except GitHubAPIError:
            # No releases found or other error
            return None

    async def get_release_by_tag(self, tag: str) -> Optional[GitHubRelease]:
        """
        Get a specific release by tag name

        Args:
            tag: Tag name (e.g., "v1.2.3")

        Returns:
            GitHubRelease or None if not found
        """
        url = f"{GITHUB_API_BASE}/repos/{self.repo}/releases/tags/{tag}"

        try:
            response = await self._make_request("GET", url)
            release_data = response.json()

            # Find asset
            asset_url = None
            asset_name = None
            asset_size = None
            for asset in release_data.get("assets", []):
                name = asset.get("name", "")
                if name.endswith(".deb"):
                    asset_url = asset.get("browser_download_url")
                    asset_name = name
                    asset_size = asset.get("size")
                    break

            release_notes = release_data.get("body", "") or ""
            asset_checksum = self._extract_checksum_from_notes(release_notes, asset_name)

            published_str = release_data.get("published_at", "")
            published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))

            return GitHubRelease(
                version=self._parse_version(release_data["tag_name"]),
                tag_name=release_data["tag_name"],
                name=release_data.get("name", release_data["tag_name"]),
                published_at=published_at,
                release_notes=release_notes,
                prerelease=release_data.get("prerelease", False),
                draft=release_data.get("draft", False),
                asset_url=asset_url,
                asset_name=asset_name,
                asset_size=asset_size,
                asset_checksum=asset_checksum,
                html_url=release_data.get("html_url"),
            )
        except GitHubAPIError:
            return None

    async def download_asset(
        self,
        asset_url: str,
        destination: Path,
        expected_checksum: Optional[str] = None,
        progress_callback: Optional[callable] = None,
    ) -> Path:
        """
        Download a release asset

        Args:
            asset_url: URL of the asset to download
            destination: Path to save the downloaded file
            expected_checksum: Optional SHA256 checksum to verify
            progress_callback: Optional callback(downloaded_bytes, total_bytes)

        Returns:
            Path to the downloaded file

        Raises:
            GitHubAPIError: If download fails
            ValueError: If checksum verification fails
        """
        logger.info("downloading_asset", url=asset_url, destination=str(destination))

        # Create parent directory if needed
        destination.parent.mkdir(parents=True, exist_ok=True)

        # Download with streaming
        client = await self._get_client()
        sha256_hash = hashlib.sha256()

        try:
            async with client.stream(
                "GET",
                asset_url,
                timeout=httpx.Timeout(DOWNLOAD_TIMEOUT),
                follow_redirects=True,
            ) as response:
                response.raise_for_status()

                total_size = int(response.headers.get("content-length", 0))
                downloaded = 0

                with open(destination, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        f.write(chunk)
                        sha256_hash.update(chunk)
                        downloaded += len(chunk)

                        if progress_callback:
                            progress_callback(downloaded, total_size)

            # Verify checksum if provided
            actual_checksum = sha256_hash.hexdigest()
            if expected_checksum:
                if actual_checksum.lower() != expected_checksum.lower():
                    # Delete the corrupted file
                    destination.unlink(missing_ok=True)
                    raise ValueError(
                        f"Checksum mismatch: expected {expected_checksum}, got {actual_checksum}"
                    )
                logger.info("checksum_verified", checksum=actual_checksum[:16])

            logger.info("download_complete", size=downloaded, checksum=actual_checksum[:16])
            return destination

        except httpx.HTTPStatusError as e:
            destination.unlink(missing_ok=True)
            raise GitHubAPIError(f"Download failed: {e.response.status_code}") from e
        except httpx.RequestError as e:
            destination.unlink(missing_ok=True)
            raise GitHubAPIError(f"Download failed: {str(e)}") from e

    async def download_checksum_file(self, release: GitHubRelease) -> Optional[str]:
        """
        Try to download a checksum file for the release

        Looks for files like "checksums.sha256" or "<asset>.sha256"

        Args:
            release: The release to get checksums for

        Returns:
            Contents of checksum file, or None if not found
        """
        if not release.asset_name:
            return None

        # Common checksum file names
        checksum_names = [
            f"{release.asset_name}.sha256",
            "checksums.sha256",
            "SHA256SUMS",
            "sha256sums.txt",
        ]

        # Build URLs based on release assets
        releases = await self.get_releases(include_prereleases=release.prerelease)
        for r in releases:
            if r.version == release.version:
                # We'd need to check the release assets for checksum files
                # For now, rely on release notes
                break

        return None

    async def get_rate_limit_status(self) -> Dict[str, Any]:
        """
        Get current GitHub API rate limit status

        Returns:
            Dict with remaining, limit, and reset time
        """
        url = f"{GITHUB_API_BASE}/rate_limit"

        try:
            response = await self._make_request("GET", url)
            data = response.json()
            core = data.get("resources", {}).get("core", {})
            return {
                "remaining": core.get("remaining", 0),
                "limit": core.get("limit", 60),
                "reset_at": datetime.fromtimestamp(core.get("reset", 0)).isoformat(),
            }
        except GitHubAPIError:
            return {"remaining": 0, "limit": 60, "reset_at": None}
