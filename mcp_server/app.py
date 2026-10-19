"""
Customer Support MCP Server (GIVEN - fully implemented)
Uses the official MCP Python SDK (FastMCP) for protocol handling and tool registration.

The server exposes 15 tools for customer and ticket management via the MCP protocol.
It uses SSE (Server-Sent Events) transport for communication.

Endpoints (managed by FastMCP):
  GET  /sse       - SSE stream for receiving responses
  POST /messages/ - Send JSON-RPC 2.0 requests
"""

import json
import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP

from config import PORT, HOST, DB_PATH, LOG_LEVEL
from database import DatabaseManager

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize database manager
db_manager = DatabaseManager(DB_PATH)
logger.info(f"Database initialized at: {DB_PATH}")

# Create MCP server using the official SDK
mcp = FastMCP("customer-support-server", host=HOST, port=PORT)


# ==================== Customer Tools ====================

@mcp.tool()
def get_customer(customer_id: int) -> str:
    """Retrieve a specific customer by their ID. Returns customer details including name, email, phone, status, and timestamps."""
    logger.info(f"[TOOL] get_customer(customer_id={customer_id})")
    result = db_manager.get_customer(customer_id)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def list_customers(status: Optional[str] = None) -> str:
    """List all customers with optional status filter. Returns a list of all customers sorted by name. Valid status values: 'active', 'disabled'."""
    logger.info(f"[TOOL] list_customers(status={status})")
    result = db_manager.list_customers(status)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def add_customer(
    name: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    status: str = "active"
) -> str:
    """Create a new customer record. Requires a name and optionally email, phone, and status ('active' or 'disabled')."""
    logger.info(f"[TOOL] add_customer(name={name})")
    result = db_manager.add_customer(name, email, phone, status)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def update_customer(
    customer_id: int,
    name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None
) -> str:
    """Update an existing customer's information. Provide the customer ID and any fields to update."""
    logger.info(f"[TOOL] update_customer(customer_id={customer_id})")
    result = db_manager.update_customer(customer_id, name, email, phone)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def disable_customer(customer_id: int) -> str:
    """Disable a customer account. The customer will be marked as 'disabled' but not deleted."""
    logger.info(f"[TOOL] disable_customer(customer_id={customer_id})")
    result = db_manager.disable_customer(customer_id)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def activate_customer(customer_id: int) -> str:
    """Activate a previously disabled customer account."""
    logger.info(f"[TOOL] activate_customer(customer_id={customer_id})")
    result = db_manager.activate_customer(customer_id)
    return json.dumps(result, indent=2, default=str)


# ==================== Ticket Tools ====================

@mcp.tool()
def get_ticket(ticket_id: int) -> str:
    """Retrieve a specific ticket by ID. Returns ticket details along with customer information."""
    logger.info(f"[TOOL] get_ticket(ticket_id={ticket_id})")
    result = db_manager.get_ticket(ticket_id)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def list_tickets(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    customer_id: Optional[int] = None
) -> str:
    """List all tickets with optional filters. Valid status: 'open', 'in_progress', 'resolved'. Valid priority: 'low', 'medium', 'high'. Can also filter by customer_id."""
    logger.info(f"[TOOL] list_tickets(status={status}, priority={priority}, customer_id={customer_id})")
    result = db_manager.list_tickets(status, priority, customer_id)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def create_ticket(
    customer_id: int,
    issue: str,
    priority: str = "medium",
    status: str = "open"
) -> str:
    """Create a new support ticket for a customer. Requires customer ID and issue description. Valid priority: 'low', 'medium', 'high'. Valid status: 'open', 'in_progress', 'resolved'."""
    logger.info(f"[TOOL] create_ticket(customer_id={customer_id}, issue={issue[:50]}...)")
    result = db_manager.create_ticket(customer_id, issue, priority, status)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def update_ticket_status(ticket_id: int, status: str) -> str:
    """Update the status of an existing ticket. Valid status: 'open', 'in_progress', 'resolved'."""
    logger.info(f"[TOOL] update_ticket_status(ticket_id={ticket_id}, status={status})")
    result = db_manager.update_ticket_status(ticket_id, status)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def update_ticket_priority(ticket_id: int, priority: str) -> str:
    """Update the priority level of an existing ticket. Valid priority: 'low', 'medium', 'high'."""
    logger.info(f"[TOOL] update_ticket_priority(ticket_id={ticket_id}, priority={priority})")
    result = db_manager.update_ticket_priority(ticket_id, priority)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def delete_ticket(ticket_id: int) -> str:
    """Delete a ticket permanently. This action cannot be undone."""
    logger.info(f"[TOOL] delete_ticket(ticket_id={ticket_id})")
    result = db_manager.delete_ticket(ticket_id)
    return json.dumps(result, default=str)


# ==================== Statistics and Search Tools ====================

@mcp.tool()
def get_ticket_stats() -> str:
    """Get statistics about tickets including counts by status and priority."""
    logger.info("[TOOL] get_ticket_stats()")
    result = db_manager.get_ticket_stats()
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def get_customer_stats() -> str:
    """Get statistics about customers including total count and count by status."""
    logger.info("[TOOL] get_customer_stats()")
    result = db_manager.get_customer_stats()
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def search_tickets(keyword: str) -> str:
    """Search for tickets by keyword in the issue description."""
    logger.info(f"[TOOL] search_tickets(keyword={keyword})")
    result = db_manager.search_tickets(keyword)
    return json.dumps(result, indent=2, default=str)


if __name__ == '__main__':
    logger.info(f"Starting Customer Support MCP Server on {HOST}:{PORT}")
    logger.info(f"Database path: {DB_PATH}")
    logger.info(f"Transport: SSE")
    logger.info(f"Endpoints: GET /sse (stream), POST /messages/ (requests)")
    logger.info(f"Available tools: 15")
    mcp.run(transport="sse")
