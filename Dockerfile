FROM ghcr.io/ibm/mcp-context-forge@sha256:7eb21fb9a8070df59435c03c76c40d8c71230c55ba89f884f2482d2cc81cff1c

# Add a configurable OIDC email-claim mapping for RFC 8707 MCP access tokens.
COPY config.py /app/mcpgateway/config.py
COPY streamablehttp_transport.py /app/mcpgateway/transports/streamablehttp_transport.py
COPY routers/well_known.py /app/mcpgateway/routers/well_known.py
COPY services/server_service.py /app/mcpgateway/services/server_service.py
