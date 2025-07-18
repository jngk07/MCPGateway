import os
import sys
import logging
import asyncio
from typing import Dict, Any
from datetime import datetime
import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
# Removing fastmcp imports since the package is not available
import fastmcp
from fastmcp.server import FastMCP
from fastmcp.server.openapi import RouteMap, RouteType
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.requests import Request
# Import FastAPI components
import uvicorn

# Helper function to validate OpenAPI schemas
def is_valid_openapi_schema(content: Dict[str, Any]) -> bool:
    """
    Check if the content is a valid OpenAPI schema.

    Args:
        content: Parsed content of a specification.

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

# Configure logger
logger = logging.getLogger("fastmcp_server")
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Add the project root to the Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

try:

    from config import Settings
    from openapi_parser import OpenAPIParser

    #logger.info("Found FastMCP version: %s", fastmcp.__version__)
    logger.info("Successfully imported all required modules")
except ImportError as e:
    logger.error("Failed to import required modules: %s", e)
    logger.error("Make sure you've installed the dependencies: pip install fastmcp")
    sys.exit(1)

# Create FastAPI app
app = FastAPI(
    title="MCP Gateway with FastMCP",
    description="MCP Gateway for API tools using FastMCP library",
    version="1.0.0",
)

# Create main FastMCP server instance
main_mcp = FastMCP("gateway")

# Dictionary to store API-specific FastMCP instances
api_mcp_servers = {}

async def setup_mcp_server():
    """Set up the MCP server with tools from the API specifications."""
    # Load settings
    settings = Settings()
    logger.info("Creating MCP server with settings: specs_dir=%s", settings.specs_dir)

    # Initialize API parser with local specs configuration
    parser = OpenAPIParser(
        specs_dir=settings.specs_dir,
        use_local_specs=settings.use_local_specs
    )

    # Configure the API fetcher for remote specs (default option)
    if settings.use_local_specs:
        logger.info("Using local API specs from directory")
        # Ensure specs directory exists when using local specs
        os.makedirs(settings.specs_dir, exist_ok=True)
    else:
        logger.info("Using remote API specs from: %s", settings.apis_list_url)
        parser.api_fetcher.apis_list_url = settings.apis_list_url
        parser.api_fetcher.api_spec_base_url = settings.api_spec_base_url

    api_specs = await parser.load_specs()
    if not api_specs:
        logger.error("No API specifications found.")

    logger.info("Loaded %d valid OpenAPI specifications", len(api_specs))
    logger.info("API specifications keys: %s", list(api_specs.keys()))

    # For every api-spec, register a FastMCP instance using FastMCP.from_openapi(spec)
    for api_name, spec in api_specs.items():
        logger.info("Processing API spec for: %s", api_name)

        # Get API info from the spec
        spec_title = spec.get("info", {}).get("title", api_name)
        versioned_api_name = f"{spec_title}"

        # Initialize default values
        parsed_api_name = spec_title.lower()  # Convert to lowercase for URL compatibility
        parsed_version = "v1"  # Default version

        # Check if title contains a version indicator
        if "-" in spec_title:
            # Split by "-" and use parts for endpoint construction
            parts = spec_title.split("-", 1)
            parsed_api_name = parts[0].lower()  # Lowercase for URL compatibility
            if len(parts) > 1:
                parsed_version = parts[1]

        # Create a simpler mount path that's more URL friendly
        mount_path = f"/{parsed_api_name}/{parsed_version}"  # Simpler path without version

        # Create AsyncClient for the API
        # First try to get the URL from servers array
        servers = spec.get("servers", [])
        api_base_url = None

        # Check for valid server URLs first
        for server in servers:
            if server.get("url"):
                api_base_url = server.get("url")
                break

        # If no valid server URL found, try to build from host (Swagger 2.0)
        if not api_base_url:
            host = spec.get("host")
            if host:
                schemes = spec.get("schemes", ["https"])
                base_path = spec.get("basePath", "/")
                api_base_url = f"{schemes[0]}://{host}{base_path}"

        # Fallback to localhost if still no URL
        if not api_base_url:
            api_base_url = "http://localhost:8765"

        api_client = httpx.AsyncClient(base_url=api_base_url)
        logger.info("Creating api client for API: %s with base URL: %s", versioned_api_name, api_base_url)

        # custom mapping rules
        custom_maps = [
            RouteMap(methods=["GET"], pattern=r".*",
             route_type=RouteType.TOOL)
        ]

        # Create a FastMCP instance for each API with custom route maps to treat any GET request as a MCP tool
        # Default mapping treats as resources for GET request with no path parameters
        # or as resource templates if GET request has path parameters
        try:
            # Check if the spec is a valid OpenAPI schema
            if not is_valid_openapi_schema(spec):
                logger.warning("Skipping API '%s' - not a valid OpenAPI schema", api_name)
                continue

            api_server = FastMCP.from_openapi(openapi_spec=spec,
                                            client=api_client,
                                            name=versioned_api_name,
                                            route_maps=custom_maps)
            api_mcp_servers[mount_path] = api_server
            logger.info("Registered FastMCP server: %s for %s", mount_path, versioned_api_name)
        except Exception as e:
            logger.error("Error creating FastMCP server for API '%s': %s", api_name, e)
            logger.error("Skipping API '%s' due to FastMCP initialization error", api_name)

    logger.info("Loaded %d APIs from specs", len(api_specs))
    return settings

@app.get("/debug", tags=["Debug"])
async def debug_info():
    """Debug endpoint showing all registered tools and endpoints."""

    # List all registered routes in the FastAPI app
    routes = []
    for route in app.routes:
        routes.append({
            "path": route.path,
            "methods": route.methods,
            "name": route.name
        })

    return {
        "apis": {},
        "all_tools": [],
        "routes": routes,
        "mcp_servers": list(api_mcp_servers.keys())
    }

@app.get("/", tags=["Health"])
async def root():
    """Root endpoint for MCP server serving as a basic health check."""
    server_info = {
        "name": "MCP Gateway with FastMCP",
        "description": "MCP Gateway for API tools using FastMCP library",
        "version": "1.0.0",
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "api_count": len(api_mcp_servers)
    }

    return server_info

# Dedicated health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for monitoring and infrastructure."""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "uptime": "unknown",  # Could be enhanced to track actual uptime
        "services": {
            "fastmcp": "available",
            "api_servers": {
                "count": len(api_mcp_servers),
                "status": "active" if len(api_mcp_servers) > 0 else "inactive"
            }
        }
    }

    return health_status

@app.get("/tools", tags=["Debug"])
async def list_tools():
    """List all available tools and their parameters."""

    return {
        "count": 0,
        "tools": []
    }

async def setup():
    """Run the MCP server."""
    logger.info("Starting MCP server with FastMCP")

    # Set up the MCP server
    await setup_mcp_server()

    # Apply CORS middleware with settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Could be configurable in settings
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Return the configured app and settings for the runner to use
    return app, api_mcp_servers

async def setup_mcp_server():
    """Set up the MCP server with tools from the API specifications."""
    # Load settings
    settings = Settings()
    logger.info("Creating MCP server with settings: specs_dir=%s", settings.specs_dir)

    # Initialize API parser with local specs configuration
    parser = OpenAPIParser(
        specs_dir=settings.specs_dir,
        use_local_specs=settings.use_local_specs
    )

    # Configure the API fetcher for remote specs (default option)
    if settings.use_local_specs:
        logger.info("Using local API specs from directory")
        # Ensure specs directory exists when using local specs
        os.makedirs(settings.specs_dir, exist_ok=True)
    else:
        logger.info("Using remote API specs from: %s", settings.apis_list_url)
        parser.api_fetcher.apis_list_url = settings.apis_list_url
        parser.api_fetcher.api_spec_base_url = settings.api_spec_base_url

    api_specs = await parser.load_specs()
    if not api_specs:
        logger.error("No API specifications found.")

    logger.info("Loaded %d valid OpenAPI specifications", len(api_specs))
    logger.info("API specifications keys: %s", list(api_specs.keys()))

    # For every api-spec, register a FastMCP instance using FastMCP.from_openapi(spec)
    for api_name, spec in api_specs.items():
        logger.info("Processing API spec for: %s", api_name)

        # Get API info from the spec
        spec_title = spec.get("info", {}).get("title", api_name)
        versioned_api_name = f"{spec_title}"

        # Initialize default values
        parsed_api_name = spec_title.lower()  # Convert to lowercase for URL compatibility
        parsed_version = "v1"  # Default version

        # Check if title contains a version indicator
        if "-" in spec_title:
            # Split by "-" and use parts for endpoint construction
            parts = spec_title.split("-", 1)
            parsed_api_name = parts[0].lower()  # Lowercase for URL compatibility
            if len(parts) > 1:
                parsed_version = parts[1]

        # Create a simpler mount path that's more URL friendly
        mount_path = f"/{parsed_api_name}/{parsed_version}"  # Simpler path without version

        # Create AsyncClient for the API
        # First try to get the URL from servers array
        servers = spec.get("servers", [])
        api_base_url = None

        # Check for valid server URLs first
        for server in servers:
            if server.get("url"):
                api_base_url = server.get("url")
                break

        # If no valid server URL found, try to build from host (Swagger 2.0)
        if not api_base_url:
            host = spec.get("host")
            if host:
                schemes = spec.get("schemes", ["https"])
                base_path = spec.get("basePath", "/")
                api_base_url = f"{schemes[0]}://{host}{base_path}"

        # Fallback to localhost if still no URL
        if not api_base_url:
            api_base_url = "http://localhost:8000"

        api_client = httpx.AsyncClient(base_url=api_base_url)
        logger.info("Creating api client for API: %s with base URL: %s", versioned_api_name, api_base_url)

        # custom mapping rules
        custom_maps = [
            RouteMap(methods=["GET"], pattern=r".*",
             route_type=RouteType.TOOL)
        ]

        # Create a FastMCP instance for each API with custom route maps to treat any GET request as a MCP tool
        # Default mapping treats as resources for GET request with no path parameters
        # or as resource templates if GET request has path parameters
        try:
            # Check if the spec is a valid OpenAPI schema
            if not is_valid_openapi_schema(spec):
                logger.warning("Skipping API '%s' - not a valid OpenAPI schema", api_name)
                continue

            api_server = FastMCP.from_openapi(openapi_spec=spec,
                                            client=api_client,
                                            name=versioned_api_name,
                                            route_maps=custom_maps)
            api_mcp_servers[mount_path] = api_server
            logger.info("Registered FastMCP server: %s for %s", mount_path, versioned_api_name)
        except Exception as e:
            logger.error("Error creating FastMCP server for API '%s': %s", api_name, e)
            logger.error("Skipping API '%s' due to FastMCP initialization error", api_name)

    logger.info("Loaded %d APIs from specs", len(api_specs))
    return settings

# Create a health check endpoint to return a simple JSON response
async def health_endpoint(request: Request):
    return JSONResponse({"status": "healthy"})

# Root endpoint to list available endpoints
async def root_endpoint(request: Request):
    endpoints = {
        "health": "/health",
        "ping": "/ping",
        "debug": "/debug",
        "tools": "/tools",
        "api_specs": "/api_specs",
        "api_specs_list": "/api_specs_list",
        "api_specs_count": "/api_specs_count",
        "api_specs_info": "/api_specs_info",
        "version": "1.0.0",
        "apis": list(api_mcp_servers.keys()) + ["/pets/v1"]
    }
    return JSONResponse(endpoints)

# main_app = Starlette()
gateway_app = FastMCP("gateway")

def main():
    """Run the MCP server with proper setup."""
    logger.info("Starting MCP server setup in main()")

    # Create a new event loop for setup and immediately get the result
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(setup())
    loop.close()

    return result

if __name__ == "__main__":
    # Call main() directly since it now handles the async setup internally
    app_config, mcp_servers = main()

    # Add MCP server routes to main app
    routes = [
        Route("/", root_endpoint, methods=["GET"]),
        Route("/health", health_endpoint, methods=["GET"])
    ]

    # Create a default FastMCP instance for the root /sse endpoint
    root_mcp = FastMCP("root-mcp")

    # Add the root SSE endpoint
    routes.append(Mount("/sse", app=root_mcp.sse_app()))

    logger.info("MCP app: %s", mcp_servers)
    # Mount each MCP server at its endpoint
    for endpoint, mcp_app in mcp_servers.items():
        logger.info("Mounting MCP server at: %s", endpoint)
        logger.info("MCP app: %s", mcp_app)
        routes.append(
            Mount(endpoint, app=mcp_app.sse_app(path='/sse'))
            )

    # # Create the Starlette app with all routes
    main_app = Starlette(routes=routes)

    # Start server with uvicorn
    logger.info("Starting unified MCP server on port 8765")
    uvicorn.run(
        main_app,
        host="0.0.0.0",
        port=8765
    )

    # Mount the root endpoint
    # gateway_app.run(
    #     transport="sse",
    #     host="0.0.0.0",
    #     port=8000
    # )
else:
    # This ensures main_mcp is initialized when imported by MCP CLI
    logger.info("MCP Server initialized for MCP CLI")
