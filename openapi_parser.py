"""
OpenAPI parser module for MCP OpenAPI Gateway.

This module handles loading and parsing OpenAPI specifications.
"""
import os
import json
import yaml
import logging
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from config import Settings

logger = logging.getLogger(__name__)

class OpenAPIParser:
    """Parser for OpenAPI specifications."""

    def __init__(self, specs_dir: str, use_local_specs: bool = False, settings: Optional[Settings] = None):
        """
        Initialize the OpenAPI parser.

        Args:
            specs_dir: Directory containing API specifications.
            use_local_specs: Whether to use local API specs instead of remote Target API.
            settings: Application settings for throttling and other configurations.
        """
        self.specs_dir = Path(specs_dir)
        self.api_specs: Dict[str, Dict[str, Any]] = {}
        self.use_local_specs = use_local_specs
        self.settings = settings or Settings()

        # Initialize API fetcher with defaults (will be configured with actual URLs later)


        # Configure throttling parameters in the API fetcher

    async def load_specs(self) -> Dict[str, Dict[str, Any]]:
        """
        Load all OpenAPI specifications from either remote API or local directory.

        Returns:
            Dictionary mapping API names to their parsed specifications.
        """
        self.api_specs = {}

        # If using local specs, load them from the directory
        if self.use_local_specs:
            logger.info("Using local API specifications from directory")
            if not self.specs_dir.exists():
                logger.warning(f"Specs directory {self.specs_dir} does not exist")
                return self.api_specs

            # Iterate through API directories
            for api_dir in self.specs_dir.iterdir():
                if not api_dir.is_dir():
                    continue

                # Find an OpenAPI spec file in the directory
                spec_file = self._find_spec_file(api_dir)
                if not spec_file:
                    logger.warning(f"No OpenAPI specification found in {api_dir}")
                    continue

                try:
                    # Parse the spec file
                    api_name = api_dir.name
                    spec = self._parse_spec_file(spec_file)
                    self.api_specs[api_name] = spec

                    # Derive base URL from servers in the API spec
                    self._update_api_base_url(api_name, spec)

                    # Log API information
                    base_path = self._get_base_path(spec)
                    servers = self._get_servers(spec)
                    logger.info(f"Loaded API spec for '{api_name}' with base path '{base_path}'")
                    logger.info(f"  Servers: {', '.join(servers) if servers else 'None defined'}")

                    # Log operations
                    operations = self.get_operations(api_name)
                    logger.info(f"  Found {len(operations)} operations")

                except ValueError as e:
                    logger.warning(f"Skipping invalid API spec file: {e}")
                except Exception as e:
                    logger.error(f"Failed to load API spec from {spec_file}: {e}")

            return self.api_specs

        # Otherwise, fetch specs from the remote API (default)
        logger.info("Using remote API specifications from Target API")
        # Properly await the async fetch method instead of using run_until_complete
        all_specs = await self.api_fetcher.fetch_all_api_specs()

        # Filter out non-OpenAPI schemas
        for api_name, spec in all_specs.items():
            if self._is_valid_openapi_schema(spec):
                self.api_specs[api_name] = spec
                # Update base URLs from the specs
                self._update_api_base_url(api_name, spec)
            else:
                logger.warning(f"Ignoring API spec for '{api_name}' - not a valid OpenAPI schema")

        logger.info(f"Loaded {len(self.api_specs)} valid OpenAPI specs out of {len(all_specs)} total specs")
        return self.api_specs

    def get_operations(self, api_name: str) -> List[Dict[str, Any]]:
        """
        Get all operations defined in an API specification.

        Args:
            api_name: Name of the API.

        Returns:
            List of operation objects with path, method, operation ID and details.
        """
        if api_name not in self.api_specs:
            return []

        spec = self.api_specs[api_name]
        operations = []

        # Extract operations from paths
        paths = spec.get("paths", {})
        for path, path_item in paths.items():
            for method, operation in path_item.items():
                if method not in ["get", "post", "put", "delete", "patch", "options", "head"]:
                    continue

                # Get or generate an operation ID
                op_id = operation.get("operationId")
                if not op_id:
                    # Generate a cleaner operationId without repeating the method
                    # Remove leading slash and replace others with underscores
                    path_part = path.lstrip('/').replace('/', '_').replace('{', '').replace('}', '')
                    op_id = f"{path_part}"

                # Resolve parameter references
                parameters = self._resolve_parameter_refs(operation.get("parameters", []), spec)

                # Extract security requirements
                security = operation.get("security", [])
                if not security and "security" in spec:
                    # If no operation-specific security, use global security
                    security = spec.get("security", [])

                # Create operation object
                operations.append({
                    "path": path,
                    "method": method,
                    "operationId": op_id,
                    "summary": operation.get("summary", ""),
                    "description": operation.get("description", ""),
                    "parameters": parameters,
                    "requestBody": operation.get("requestBody"),
                    "responses": operation.get("responses", {}),
                    "security": security
                })

        return operations

    def _resolve_parameter_refs(self, parameters: List[Dict[str, Any]], spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Resolve parameter references in OpenAPI spec.

        Args:
            parameters: List of parameters that may contain $ref.
            spec: The full API specification.

        Returns:
            List of resolved parameters.
        """
        resolved_params = []

        for param in parameters:
            if "$ref" in param:
                ref_path = param["$ref"]
                # Handle '#/components/parameters/xxx' style references
                if ref_path.startswith("#/"):
                    parts = ref_path[2:].split("/")
                    ref_value = spec
                    for part in parts:
                        if part in ref_value:
                            ref_value = ref_value[part]
                        else:
                            logger.warning(f"Could not resolve reference: {ref_path}")
                            ref_value = {}
                            break

                    if ref_value:
                        resolved_params.append(ref_value)
            else:
                resolved_params.append(param)

        return resolved_params

    def get_api_info(self, api_name: str) -> Dict[str, Any]:
        """
        Get information about an API.

        Args:
            api_name: Name of the API.

        Returns:
            Dictionary with API information.
        """
        if api_name not in self.api_specs:
            return {}

        spec = self.api_specs[api_name]
        info = spec.get("info", {})

        # Extract API information
        return {
            "name": api_name,
            "title": info.get("title", api_name),
            "version": info.get("version", ""),
            "description": info.get("description", ""),
            "base_path": self._get_base_path(spec),
            "servers": self._get_servers(spec),
        }

    def _find_spec_file(self, api_dir: Path) -> Optional[Path]:
        """
        Find an OpenAPI specification file in a directory.

        Args:
            api_dir: Directory to search in.

        Returns:
            Path to the spec file if found, None otherwise.
        """
        # Common filenames for OpenAPI specifications
        common_filenames = [
            "openapi.yaml", "openapi.yml", "openapi.json",
            "swagger.yaml", "swagger.yml", "swagger.json",
            "api.yaml", "api.yml", "api.json",
        ]

        # Check for common filenames first
        for filename in common_filenames:
            spec_path = api_dir / filename
            if spec_path.exists():
                return spec_path

        # Otherwise, look for any YAML or JSON file
        for file_path in api_dir.glob("*.yaml"):
            return file_path
        for file_path in api_dir.glob("*.yml"):
            return file_path
        for file_path in api_dir.glob("*.json"):
            return file_path

        return None

    def _parse_spec_file(self, spec_file: Path) -> Dict[str, Any]:
        """
        Parse an OpenAPI specification file.

        Args:
            spec_file: Path to the specification file.

        Returns:
            Parsed specification as a dictionary.

        Raises:
            ValueError: If the file format is not supported or if it's not a valid OpenAPI schema.
        """
        try:
            with open(spec_file, "r") as f:
                if spec_file.suffix in [".yaml", ".yml"]:
                    content = yaml.safe_load(f)
                elif spec_file.suffix == ".json":
                    content = json.load(f)
                else:
                    raise ValueError(f"Unsupported file format: {spec_file.suffix}")

                # Validate that it's an OpenAPI specification
                if not self._is_valid_openapi_schema(content):
                    logger.warning(f"File {spec_file} is not a valid OpenAPI schema, ignoring")
                    raise ValueError(f"Not a valid OpenAPI schema: {spec_file}")

                return content
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML file {spec_file}: {e}")
            raise ValueError(f"Invalid YAML format in {spec_file}")
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON file {spec_file}: {e}")
            raise ValueError(f"Invalid JSON format in {spec_file}")

    def _is_valid_openapi_schema(self, content: Dict[str, Any]) -> bool:
        """
        Check if the content is a valid OpenAPI schema.

        Args:
            content: Parsed content of a file.

        Returns:
            True if it's a valid OpenAPI schema, False otherwise.
        """
        # OpenAPI 3.0 specification should have 'openapi' field
        if 'openapi' in content:
            # Check if it matches the pattern '3.x.x'
            version = content['openapi']
            if isinstance(version, str) and version.startswith('3.'):
                return True

        # Swagger 2.0 specification should have 'swagger' field with value '2.0'
        if 'swagger' in content:
            version = content['swagger']
            if version == '2.0':
                return True

        # Not a valid OpenAPI schema
        return False

    def _get_base_path(self, spec: Dict[str, Any]) -> str:
        """
        Get the base path for an API.

        Args:
            spec: API specification.

        Returns:
            Base path string.
        """
        # Try to extract from servers array first
        servers = self._get_servers(spec)
        if servers:
            for url in servers:
                # Remove protocol and domain if present
                if "://" in url:
                    url_parts = url.split("://")[1].split("/", 1)
                    if len(url_parts) > 1:
                        return f"/{url_parts[1]}"

        # Fallback to basePath from Swagger 2.0
        return spec.get("basePath", "/")

    def _get_servers(self, spec: Dict[str, Any]) -> List[str]:
        """
        Get server URLs from an API specification.

        Args:
            spec: API specification.

        Returns:
            List of server URLs.
        """
        # First try to get from standard servers array
        servers = spec.get("servers", [])
        server_urls = [server.get("url") for server in servers if "url" in server and server.get("url")]

        if server_urls:
            return server_urls

        # If no standard servers, check for custom x-api-definition endpoints
        if "x-api-definition" in spec and "endpoints" in spec["x-api-definition"]:
            endpoints = spec["x-api-definition"]["endpoints"]
            custom_urls = []

            # Add external endpoints
            if "external" in endpoints:
                for env, url in endpoints["external"].items():
                    if url:  # Skip null values
                        custom_urls.append(url)

            # Add internal endpoints
            if "internal" in endpoints:
                for env, url in endpoints["internal"].items():
                    if url:  # Skip null values
                        custom_urls.append(url)

            if custom_urls:
                return custom_urls

        # If we still don't have servers, try to build from host + schemes (Swagger 2.0)
        host = spec.get("host")
        schemes = spec.get("schemes", ["https"])
        base_path = spec.get("basePath", "/")

        if host:
            return [f"{scheme}://{host}{base_path}" for scheme in schemes]

        # Default empty list if no server URLs found
        return []

    def _update_api_base_url(self, api_name: str, spec: Dict[str, Any]) -> None:
        """
        Update the base URL for an API using information from the OpenAPI spec.

        Args:
            api_name: Name of the API.
            spec: API specification.
        """
        # Check if there's already a configured base URL for this API
        if hasattr(self.settings, "api_base_urls") and api_name in self.settings.api_base_urls:
            logger.debug(f"Using configured base URL for {api_name}")
            return

        # Try to get server URLs from the spec
        servers = self._get_servers(spec)
        if not servers:
            logger.warning(f"No servers defined for {api_name}")
            return

        # Use the first server URL as the base URL
        base_url = servers[0]
        logger.debug(f"Setting base URL for {api_name} to {base_url}")

        # Update the API base URLs in settings
        if not hasattr(self.settings, "api_base_urls"):
            self.settings.api_base_urls = {}

        self.settings.api_base_urls[api_name] = base_url
