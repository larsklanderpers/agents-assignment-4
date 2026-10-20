"""
Support Agent
Root agent declaration for ADK Web testing

NOTE: root_agent is created at import time for ADK Web.
You must implement create_agent() in agent.py before running `adk web`.
"""

from .agent import create_agent

# Root agent - required for ADK Web
# This will raise NotImplementedError until you implement create_agent()
try:
    root_agent = create_agent()
except NotImplementedError:
    root_agent = None
    print("[WARN] support_agent: create_agent() not implemented yet."
          " Implement it in agents/support_agent/agent.py")
