import logging
from typing import Dict, Any, Optional
from pydantic import Field
from pydantic_settings import BaseSettings

logger = logging.getLogger("fastmcp_server")

class Settings(BaseSettings):
    """
    Configuration settings for the FastMCP server.
    """
    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000

    specs_dir : str = Field(default="api_specs", description="Directory to store API specifications")

    logger.info("SPEC=%s", specs_dir)

    server_name: str = Field(default="openapi-gateway", description="Name of the server")
    server_version: str = Field(default="1.0.0", description="Version of the server")

    api_base_urls: Dict[str, str] = Field(
        default_factory=dict,
        description="Base URLs for different APIs. Example: {'api1': 'http://api1.example.com', 'api2': 'http://api2.example.com'}"
    )

    api_headers: Dict[str, Dict[str, str]] = Field(
        default_factory=lambda: {
            "bikes": {
                "User-Agent": "fastmcp/1.0.0",
                "Accept": "application/json",
            },
            "pets": {
                "User-Agent": "fastmcp/1.0.0",
                "Accept": "application/json",
            },
            "news": {
                "User-Agent": "fastmcp/1.0.0",
                "Accept": "application/json",
            },
        },
        description="Headers to be sent with requests to different APIs. Example: {'api1': {'Header1': 'Value1'}, 'api2': {'Header2': 'Value2'}}"
    )

    tool_prefix: str = Field(
        default="tool",
        description="Prefix for tool names. Example: 'tool' will create tools like 'tool1', 'tool2', etc."
    )

    api_timeout: float = Field(
        default=5.0,
        description="Timeout for API requests in seconds. Default is 5 seconds."
    )

    default_headers: Dict[str, str] = Field(
        default_factory= dict,
        description="Default headers to be sent with requests to APIs."
    )

    request_delay: float = Field(
        default=0.0,
        description="Delay between requests to APIs in seconds. Default is 0 seconds."
    )
    max_retries: int = Field(
        default=3,
        description="Maximum number of retries for API requests. Default is 3."
    )
    retry_delay: float = Field(
        default=1.0,
        description="Delay between retries in seconds. Default is 1 second."
    )
    retry_status_codes: list = Field(
        default_factory=lambda: [500, 502, 503, 504],
        description="HTTP status codes that should trigger a retry. Default is [500, 502, 503, 504]."
    )
    retry_methods: list = Field(
        default_factory=lambda: ["GET", "POST"],
        description="HTTP methods that should trigger a retry. Default is ['GET', 'POST']."
    )
    max_connections: int = Field(
        default=100,
        description="Maximum number of connections to the server. Default is 100."
    )

    use_local_specs: bool = Field(
        default=True,
        description="Use local API specifications instead of fetching from the server. Default is False."
    )

    apis_list_url: str = Field(
        default="https://api.example.com/apis",
        description="URL to fetch the list of APIs. Default is 'https://api.example.com/apis'."
    )
    api_specs_base_url: str = Field(
        default="https://api.example.com/specs",
        description="URL to fetch the API specifications. Default is 'https://api.example.com/specs'."
    )

    verify_ssl: bool = Field(
        default=False,
        description="Verify SSL certificates. Default is True."
    )

    class config:
        env_file = ".env"
        env_prefix = "MCP_"
        env_file_encoding = "utf-8"
        case_sensitive = True
        use_enum_values = True
        arbitrary_types_allowed = True

    def __init__(self, **kwargs: Any):
        """
        Initialize the Settings class with default values and environment variables.
        """
        if 'port' in kwargs and not isinstance(kwargs['port'], int):
            try:
                kwargs['port'] = int(kwargs['port'])
            except (ValueError, TypeError):
                 kwargs['port'] = 8000


        super().__init__(**kwargs)
