"""A2A discovery cards and factories for the three-agent support system."""

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    TransportProtocol,
)
from shared.agents_config import (
    CUSTOMER_DATA_AGENT_URL,
    SUPPORT_AGENT_URL,
    HOST_AGENT_URL,
    CUSTOMER_DATA_AGENT_PORT,
    SUPPORT_AGENT_PORT,
    HOST_AGENT_PORT,
)

# Import agent creation functions
from customer_data_agent.agent import create_agent as create_customer_data_agent
from support_agent.agent import create_agent as create_support_agent
from host_agent.agent import create_agent as create_host_agent


# =============================================================================
# Customer Data Agent Card (5 pts)
# =============================================================================

def create_customer_data_agent_card() -> AgentCard:
    """Advertise Customer Data Agent capabilities for A2A discovery."""
    return AgentCard(
        name='Customer Data Agent',
        url=CUSTOMER_DATA_AGENT_URL,
        description='Access and manage customer records, support tickets, and statistics.',
        version='1.0',
        capabilities=AgentCapabilities(streaming=True),
        default_input_modes=['text/plain'],
        default_output_modes=['application/json'],
        preferred_transport=TransportProtocol.jsonrpc,
        skills=[AgentSkill(
            id='manage_customer_data', name='Customer Data Agent',
            description='Access and manage customer records, support tickets, and statistics.',
            tags=['customers', 'tickets', 'data'],
            examples=['Get customer 5 information', 'Show open high-priority tickets'],
        )],
    )


# =============================================================================
# Support Agent Card (5 pts)
# =============================================================================

def create_support_agent_card() -> AgentCard:
    """Advertise Support Agent capabilities for A2A discovery."""
    return AgentCard(
        name='Support Agent',
        url=SUPPORT_AGENT_URL,
        description='Troubleshoot customer issues and manage support tickets.',
        version='1.0',
        capabilities=AgentCapabilities(streaming=True),
        default_input_modes=['text/plain'],
        default_output_modes=['text/plain'],
        preferred_transport=TransportProtocol.jsonrpc,
        skills=[AgentSkill(
            id='provide_support', name='Support Agent',
            description='Troubleshoot customer issues and manage support tickets.',
            tags=['support', 'troubleshooting'],
            examples=['Help me reset my password', 'My payment failed; what should I do?'],
        )],
    )


# =============================================================================
# Host Agent Card (5 pts)
# =============================================================================

def create_host_agent_card() -> AgentCard:
    """Advertise Customer Support Host Agent capabilities for A2A discovery."""
    return AgentCard(
        name='Customer Support Host Agent',
        url=HOST_AGENT_URL,
        description='Coordinate customer data lookup and support guidance using A2A.',
        version='1.0',
        capabilities=AgentCapabilities(streaming=True),
        default_input_modes=['text/plain'],
        default_output_modes=['text/plain'],
        preferred_transport=TransportProtocol.jsonrpc,
        skills=[AgentSkill(
            id='comprehensive_support', name='Customer Support Host Agent',
            description='Coordinate customer data lookup and support guidance using A2A.',
            tags=['orchestration', 'support', 'data'],
            examples=[
                'Check customer 5 and help with login problems',
                'Show my open tickets and help resolve them',
            ],
        )],
    )


# =============================================================================
# Factory Function (5 pts)
# =============================================================================

def create_all_agents() -> dict:
    """Build all three agents with their cards and configured server ports."""
    return {
        'customer_data': {
            'agent': create_customer_data_agent(),
            'card': create_customer_data_agent_card(),
            'port': CUSTOMER_DATA_AGENT_PORT,
        },
        'support': {
            'agent': create_support_agent(),
            'card': create_support_agent_card(),
            'port': SUPPORT_AGENT_PORT,
        },
        'host': {
            'agent': create_host_agent(),
            'card': create_host_agent_card(),
            'port': HOST_AGENT_PORT,
        },
    }
