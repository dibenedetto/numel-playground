# event_bus

import asyncio
import json


from   datetime import datetime
from   enum     import Enum
from   fastapi  import WebSocket
from   pydantic import BaseModel
from   typing   import Any, Callable, Dict, List, Optional, Set


class EventType(str, Enum):
	# System events
	ERROR                    = "error"
	WARNING                  = "warning"
	INFO                     = "info"

	# Manager events
	MANAGER_CLEARED          = "manager.cleared"
	MANAGER_WORKFLOW_CREATED = "manager.workflow_created"
	MANAGER_WORKFLOW_ADDED   = "manager.workflow_added"
	MANAGER_WORKFLOW_REMOVED = "manager.workflow_removed"
	MANAGER_WORKFLOW_GOT     = "manager.workflow_got"
	MANAGER_WORKFLOW_IMPL    = "manager.workflow_impl"
	MANAGER_WORKFLOW_LISTED  = "manager.workflow_listed"
	MANAGER_UPLOAD_ADDED     = "manager.upload_added"
	MANAGER_UPLOAD_REMOVED   = "manager.upload_removed"
	MANAGER_UPLOAD_GOT       = "manager.upload_got"

	# Workflow events
	WORKFLOW_STARTED         = "workflow.started"
	WORKFLOW_COMPLETED       = "workflow.completed"
	WORKFLOW_FAILED          = "workflow.failed"
	WORKFLOW_PAUSED          = "workflow.paused"
	WORKFLOW_RESUMED         = "workflow.resumed"
	WORKFLOW_CANCELLED       = "workflow.cancelled"

	# Node events
	NODE_STARTED             = "node.started"
	NODE_COMPLETED           = "node.completed"
	NODE_FAILED              = "node.failed"
	NODE_SKIPPED             = "node.skipped"
	NODE_WAITING             = "node.waiting"

	# Edge events
	EDGE_TRAVERSED           = "edge.traversed"
	EDGE_CONDITION_EVALUATED = "edge.condition_evaluated"

	# Data events
	DATA_UPDATED             = "data.updated"
	VARIABLE_CHANGED         = "variable.changed"

	# User events
	USER_INPUT_REQUESTED     = "user_input.requested"
	USER_INPUT_RECEIVED      = "user_input.received"

	# File upload events
	UPLOAD_STARTED           = "upload.started"
	UPLOAD_COMPLETED         = "upload.completed"
	UPLOAD_FAILED            = "upload.failed"

	# Processing events
	PROCESSING_STARTED       = "processing.started"
	PROCESSING_COMPLETED     = "processing.completed"
	PROCESSING_FAILED        = "processing.failed"



class WorkflowEvent(BaseModel):
	event_id     : str
	event_type   : EventType
	timestamp    : str
	workflow_id  : Optional[str]            = None
	execution_id : Optional[str]            = None
	node_id      : Optional[str]            = None
	edge_id      : Optional[str]            = None
	data         : Optional[Dict[str, Any]] = None
	error        : Optional[str]            = None


class EventBus:
	"""
	Central event bus for workflow execution events.
	Supports both local subscribers and WebSocket clients.
	"""

	def __init__(self):
		self._subscribers       : Dict[EventType, List[Callable]] = {}
		self._websocket_clients : Set[WebSocket]                  = set()
		self._event_history     : List[WorkflowEvent]             = []
		self._max_history       : int                             = 1000
		self._event_counter     : int                             = 0


	def subscribe(self, event_type: EventType, callback: Callable):
		"""Subscribe to specific event type"""
		if event_type not in self._subscribers:
			self._subscribers[event_type] = []
		self._subscribers[event_type].append(callback)


	def unsubscribe(self, event_type: EventType, callback: Callable):
		"""Unsubscribe from specific event type"""
		if event_type in self._subscribers:
			self._subscribers[event_type].remove(callback)


	async def publish(self, event: WorkflowEvent):
		"""Publish event to all subscribers and WebSocket clients"""
		# Add to history
		self._event_history.append(event)
		if len(self._event_history) > self._max_history:
			self._event_history.pop(0)

		# Notify local subscribers
		if event.event_type in self._subscribers:
			for callback in self._subscribers[event.event_type]:
				try:
					if asyncio.iscoroutinefunction(callback):
						await callback(event)
					else:
						callback(event)
				except Exception as e:
					print(f"Error in event subscriber: {e}")

		# Notify WebSocket clients
		await self._broadcast_to_websockets(event)


	async def _broadcast_to_websockets(self, event: WorkflowEvent):
		"""Broadcast event to all connected WebSocket clients"""
		if not self._websocket_clients:
			return

		message = json.dumps({
			"type"  : "workflow_event",
			"event" : event.model_dump()
		})

		dead_clients = set()
		for client in self._websocket_clients:
			try:
				await client.send_text(message)
			except Exception:
				dead_clients.add(client)

		# Remove dead clients
		self._websocket_clients -= dead_clients


	async def add_websocket_client(self, websocket: WebSocket):
		"""Add WebSocket client to receive events"""
		await websocket.accept()
		self._websocket_clients.add(websocket)

		# Send recent history to new client
		if self._event_history:
			history_message = json.dumps({
				"type": "event_history",
				"events": [e.model_dump() for e in self._event_history[-50:]]
			})
			await websocket.send_text(history_message)


	def remove_websocket_client(self, websocket: WebSocket):
		"""Remove WebSocket client"""
		self._websocket_clients.discard(websocket)


	def get_event_history(self,
		workflow_id  : Optional[str]       = None,
		execution_id : Optional[str]       = None,
		event_type   : Optional[EventType] = None,
		limit        : int                 = 100
	) -> List[WorkflowEvent]:
		"""Get filtered event history"""
		events = self._event_history

		if workflow_id:
			events = [e for e in events if e.workflow_id == workflow_id]
		if execution_id:
			events = [e for e in events if e.execution_id == execution_id]
		if event_type:
			events = [e for e in events if e.event_type == event_type]

		return events[-limit:]


	def clear_history(self):
		"""Clear event history"""
		self._event_history.clear()


	def _generate_event_id(self) -> str:
		"""Generate unique event ID"""
		self._event_counter += 1
		timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
		return f"evt_{timestamp}_{self._event_counter}"


	async def emit(self,
		event_type   : EventType,
		workflow_id  : Optional[str]            = None,
		execution_id : Optional[str]            = None,
		node_id      : Optional[str]            = None,
		edge_id      : Optional[str]            = None,
		data         : Optional[Dict[str, Any]] = None,
		error        : Optional[str]            = None
	):
		"""Helper to create and publish event"""
		event = WorkflowEvent(
			event_id     = self._generate_event_id(),
			event_type   = event_type,
			timestamp    = datetime.now().isoformat(),
			workflow_id  = workflow_id,
			execution_id = execution_id,
			node_id      = node_id,
			edge_id      = edge_id,
			data         = data,
			error        = error
		)
		await self.publish(event)


# Global event bus instance
_global_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
	"""Get or create global event bus instance"""
	global _global_event_bus
	if _global_event_bus is None:
		_global_event_bus = EventBus()
	return _global_event_bus


def reset_event_bus():
	"""Reset global event bus (useful for testing)"""
	global _global_event_bus
	_global_event_bus = None
