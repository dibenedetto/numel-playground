"""
Tutorial Extension - Schema Definition (REFERENCE FILE)
=========================================================

NOTE: This is a REFERENCE FILE for documentation purposes.
The actual Counter class is defined in schema.py to ensure it's
transmitted to the frontend with the rest of the schema.

This file demonstrates the pattern for creating new node types.
When creating your own nodes, add them directly to schema.py
following this pattern.

See docs/tutorial-extension.md for full documentation.
"""

# =============================================================================
# EXAMPLE: HOW TO DEFINE A NEW NODE TYPE
# =============================================================================
#
# 1. Import required types:
#
#     from pydantic import Field
#     from typing import Annotated, Literal
#
# 2. Choose a base class:
#     - BaseType: Basic node without special behavior
#     - InteractiveType: Node that responds to user actions (buttons, etc.)
#     - ConfigType: Configuration/settings node
#     - FlowType: Workflow flow control node
#
# 3. Add decorators (order matters - buttons appear left-to-right):
#
#     @node_button(id="action", label="Do It", icon="!", position="bottom")
#     @node_info(title="My Node", description="...", icon="X", section="MySection", visible=True)
#     class MyNode(InteractiveType):
#         ...
#
# 4. Define fields with FieldRole annotations:
#
#     class MyNode(InteractiveType):
#         # Hidden constant - identifies node type for serialization
#         type: Annotated[Literal["my_node"], FieldRole.CONSTANT] = "my_node"
#
#         # Output slot - other nodes can connect to receive this value
#         result: Annotated[int, FieldRole.OUTPUT] = 0
#
#         # Input slot - other nodes can connect to provide this value
#         config: Annotated[str, FieldRole.INPUT] = "default"
#
#         # Property - editable in properties panel, not a connection slot
#         name: Annotated[str, FieldRole.PROPERTY] = "unnamed"
#
# =============================================================================
# COUNTER NODE (defined in schema.py)
# =============================================================================
#
# @node_button(id="reset", label="Reset", icon="0", position="bottom")
# @node_button(id="decrement", label="-", icon="-", position="bottom")
# @node_button(id="increment", label="+", icon="+", position="bottom")
# @node_info(
#     title="Counter",
#     description="A simple counter that can be incremented, decremented, or reset.",
#     icon="#",
#     section="Tutorial",
#     visible=True
# )
# class Counter(InteractiveType):
#     type  : Annotated[Literal["counter"], FieldRole.CONSTANT] = "counter"
#     value : Annotated[int               , FieldRole.OUTPUT  ] = 0
#     step  : Annotated[int               , FieldRole.INPUT   ] = 1
