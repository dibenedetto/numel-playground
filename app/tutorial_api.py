"""
Tutorial Extension - API Endpoints
===================================

This file demonstrates how to create API endpoints for custom node types.
It defines the /counter endpoint that handles increment, decrement, and reset actions.

Key concepts covered:
- Defining request models with Pydantic
- Creating POST endpoints with FastAPI
- Accessing the workflow and node data
- Updating node values and returning responses

Integration:
    Add this code to api.py inside the setup_api() function, or import and call
    setup_tutorial_api() from within setup_api().
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Optional

from manager import WorkflowManager
from utils import log_print


# =============================================================================
# REQUEST MODELS
# =============================================================================

class CounterRequest(BaseModel):
    """
    Request model for counter operations.

    Attributes:
        node_index: The index of the Counter node in the workflow
        action: The action to perform ('increment', 'decrement', 'reset')
        step: Optional step override (uses node's step value if not provided)
    """
    node_index: int
    action: str  # 'increment', 'decrement', 'reset'
    step: Optional[int] = None


# =============================================================================
# API SETUP
# =============================================================================

def setup_tutorial_api(app: FastAPI, manager: WorkflowManager):
    """
    Set up tutorial API endpoints.

    Call this function from within setup_api() in api.py:
        from tutorial_api import setup_tutorial_api
        setup_tutorial_api(app, manager)

    Args:
        app: The FastAPI application instance
        manager: The WorkflowManager for accessing workflow data
    """

    @app.post("/counter")
    async def counter_action(request: CounterRequest):
        """
        Handle counter node actions (increment, decrement, reset).

        This endpoint demonstrates:
        - Accessing the current workflow implementation
        - Finding a node by index
        - Validating node type
        - Modifying node values
        - Returning structured responses
        """
        try:
            # Get the current workflow implementation
            impl = await manager.impl()
            if not impl:
                raise HTTPException(status_code=404, detail="No active workflow")

            workflow = impl["workflow"]

            # Validate node index
            node_index = request.node_index
            if node_index < 0 or node_index >= len(workflow.nodes):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid node index: {node_index}"
                )

            # Get the node and validate its type
            node = workflow.nodes[node_index]
            if node.type != "counter":
                raise HTTPException(
                    status_code=400,
                    detail=f"Node at index {node_index} is not a counter (got {node.type})"
                )

            # Get current value and step
            current_value = getattr(node, 'value', 0) or 0
            step = request.step if request.step is not None else getattr(node, 'step', 1) or 1

            # Perform the requested action
            action = request.action.lower()
            if action == 'increment':
                new_value = current_value + step
            elif action == 'decrement':
                new_value = current_value - step
            elif action == 'reset':
                new_value = 0
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown action: {action}. Use 'increment', 'decrement', or 'reset'"
                )

            # Update the node value
            node.value = new_value

            # Log the action (optional, for debugging)
            log_print(f"[Counter] Node {node_index}: {action} -> {new_value}")

            # Return the result
            return {
                "status": "success",
                "node_index": node_index,
                "action": action,
                "previous_value": current_value,
                "new_value": new_value,
                "step": step
            }

        except HTTPException:
            raise
        except Exception as e:
            log_print(f"[Counter] Error: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
