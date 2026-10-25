"""
Part 3: Host Agent / Orchestrator (20 points)

Create a SequentialAgent that coordinates between Customer Data Agent and Support Agent
using the A2A (Agent-to-Agent) protocol.

This is the core of the assignment: connecting remote agents via A2A.

Architecture:
  Host Agent (SequentialAgent)
    -> RemoteA2aAgent("customer_data") -- calls Customer Data Agent via A2A
    -> RemoteA2aAgent("support_specialist") -- calls Support Agent via A2A

Requirements:
  - Import and apply the A2A compatibility patch (CRITICAL) (2 pts)
  - Create RemoteA2aAgent for Customer Data Agent (6 pts)
  - Create RemoteA2aAgent for Support Agent (6 pts)
  - Create SequentialAgent combining both remote agents (6 pts)

Key concepts:
  - RemoteA2aAgent wraps a remote agent as a local sub-agent
  - agent_card URL = agent_url + AGENT_CARD_WELL_KNOWN_PATH
  - SequentialAgent runs sub-agents in order, passing context between them
"""

import sys
import os
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# =============================================================================
# CRITICAL: Apply A2A compatibility patch BEFORE importing RemoteA2aAgent
# This fixes an import issue between google-adk and a2a-sdk versions.
# =============================================================================
from shared import a2a_compat  # noqa: F401

from google.adk.agents import SequentialAgent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH
from shared.agents_config import (
    CUSTOMER_DATA_AGENT_URL,
    SUPPORT_AGENT_URL,
)

# Configure logging for this agent
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [HOST_AGENT] %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def create_agent() -> SequentialAgent:
    """Run customer-data lookup followed by support over remote A2A endpoints."""
    return SequentialAgent(
        name='customer_support_host',
        sub_agents=[
            RemoteA2aAgent(
                name='customer_data',
                description='Access customer and ticket data from MCP server',
                agent_card=f'{CUSTOMER_DATA_AGENT_URL}{AGENT_CARD_WELL_KNOWN_PATH}',
            ),
            RemoteA2aAgent(
                name='support_specialist',
                description='Provide customer support and troubleshooting solutions',
                agent_card=f'{SUPPORT_AGENT_URL}{AGENT_CARD_WELL_KNOWN_PATH}',
            ),
        ],
    )
