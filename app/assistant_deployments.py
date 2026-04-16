from __future__ import annotations

import asyncio
import contextlib
import json
import os
import uuid

from datetime import datetime, timedelta
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from assistant_memory_contract import normalize_assistant_memory_config, resolve_assistant_memory_db_path
from assistant_network_workflow import build_assistant_network_workflow, parse_assistant_network_workflow_import
from assistant_proactive_workflow import build_assistant_proactive_workflow
from channels.base import ChannelConfig, ChannelStatus
from event_bus import EventType
from engine import WorkflowEngine
from backend_factory import build_backend
from runtime_settings import get_runtime_settings
from runtime_toolkit_bindings import bind_runtime_toolkits_to_workflow
from runtime_workflow import workflow_from_payload
from utils import log_print
from workflow_backed_runtime import run_workflow_backed_agent_turn


_CONFIG_PATH = str(get_runtime_settings().assistant_deployments_path)


def _now_iso() -> str:
    return datetime.now().isoformat()


def _proactive_key(deployment_id: str, task_id: str) -> str:
    return f"{deployment_id}:{task_id}"


def _proactive_source_id(deployment_id: str, task_id: str) -> str:
    return f"deploy_proactive_{deployment_id}_{task_id}"


_PROACTIVE_TRIGGER_KINDS = {"timer", "fswatch", "webhook", "channel", "browser"}
_HANDOFF_SELECTOR_MODES = {"keyword", "hybrid", "workflow"}


class AssistantRoutingRule(BaseModel):
    id: str = Field(default_factory=lambda: f"route_{uuid.uuid4().hex[:8]}")
    name: str = ""
    target_deployment_id: str
    keywords: List[str] = Field(default_factory=list)
    enabled: bool = True


class AssistantProactiveTask(BaseModel):
    id: str = Field(default_factory=lambda: f"proactive_{uuid.uuid4().hex[:8]}")
    name: str
    prompt: str
    interval_sec: int = 900
    trigger_kind: str = "timer"
    trigger: Optional[Dict[str, Any]] = None
    channel_id: Optional[str] = None
    recipient_id: Optional[str] = None
    enabled: bool = True
    send_response: bool = True


class AssistantSafetyConfig(BaseModel):
    proactive_delivery_mode: Literal["auto", "approval"] = "auto"
    tool_execution_mode: Literal["auto", "approval"] = "auto"


class AssistantDeploymentConfig(BaseModel):
    id: str = Field(default_factory=lambda: f"deploy_{uuid.uuid4().hex[:8]}")
    name: str
    profile: str = "general"
    description: str = ""
    instructions: str = ""
    linked_space_id: Optional[str] = None
    linked_space_title: Optional[str] = None
    linked_workflow_name: Optional[str] = None
    model_source: Optional[str] = None
    model_name: Optional[str] = None
    toolkit_names: List[str] = Field(default_factory=list)
    skill_names: List[str] = Field(default_factory=list)
    channel_ids: List[str] = Field(default_factory=list)
    handoff_selector_mode: Literal["keyword", "hybrid", "workflow"] = "hybrid"
    handoff_selector_prompt: str = ""
    routing_rules: List[AssistantRoutingRule] = Field(default_factory=list)
    proactive_tasks: List[AssistantProactiveTask] = Field(default_factory=list)
    safety: AssistantSafetyConfig = Field(default_factory=AssistantSafetyConfig)
    enabled: bool = False
    auto_start: bool = False
    created_by: Optional[str] = None
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)


class AssistantDeploymentManager:
    """Persisted assistant deployments that bind channel endpoints to assistant config."""

    def __init__(self, config_path: str = _CONFIG_PATH):
        self._config_path = config_path
        self._deployments: Dict[str, AssistantDeploymentConfig] = {}
        self._channel_registry = None
        self._channel_pool = None
        self._runtime_stats: Dict[str, Dict[str, Any]] = {}
        self._handoff_history: List[Dict[str, Any]] = []
        self._message_history: List[Dict[str, Any]] = []
        self._endpoint_history: List[Dict[str, Any]] = []
        self._proactive_history: List[Dict[str, Any]] = []
        self._pending_proactive_approvals: Dict[str, Dict[str, Any]] = {}
        self._pending_tool_approvals: Dict[str, Dict[str, Any]] = {}
        self._approval_history: List[Dict[str, Any]] = []
        self._tool_approval_history: List[Dict[str, Any]] = []
        self._conversation_handoffs: Dict[str, Dict[str, Any]] = {}
        self._proactive_runtime: Dict[str, Dict[str, Any]] = {}
        self._proactive_loops: Dict[str, asyncio.Task] = {}
        self._proactive_event_bus = None
        self._proactive_engine: Optional[WorkflowEngine] = None
        self._proactive_execution_meta: Dict[str, Dict[str, Any]] = {}
        self._proactive_execution_index: Dict[str, str] = {}
        self._skill_mgr = None

    def initialize(self, channel_registry=None, channel_pool=None, event_bus=None):
        self._channel_registry = channel_registry
        self._channel_pool = channel_pool
        self._proactive_event_bus = event_bus
        if event_bus is not None:
            self._proactive_engine = WorkflowEngine(
                event_bus,
                channel_registry=channel_registry,
                assistant_deployment_mgr=self,
                channel_pool=channel_pool,
            )
            event_bus.subscribe(EventType.NODE_COMPLETED, self._on_proactive_node_completed)
            event_bus.subscribe(EventType.WORKFLOW_COMPLETED, self._on_proactive_workflow_completed)
            event_bus.subscribe(EventType.WORKFLOW_FAILED, self._on_proactive_workflow_failed)
            event_bus.subscribe(EventType.WORKFLOW_CANCELLED, self._on_proactive_workflow_cancelled)
        self._load()
        log_print(f"Assistant deployments initialized ({len(self._deployments)} deployments)")

    def set_channel_pool(self, channel_pool) -> None:
        self._channel_pool = channel_pool
        if self._proactive_engine is not None:
            self._proactive_engine.set_runtime_services(
                channel_registry=self._channel_registry,
                assistant_deployment_mgr=self,
                channel_pool=channel_pool,
            )

    def set_skill_mgr(self, skill_mgr) -> None:
        self._skill_mgr = skill_mgr

    def _runtime_memory_db_path(self, identity: Optional[str]) -> Optional[str]:
        return resolve_assistant_memory_db_path(
            user_memory_db=getattr(self._channel_pool, "_user_memory_db", None),
            identity=identity,
            fallback_config_path=getattr(self._channel_pool, "_config_path", None) or self._config_path,
            backend_name="agno",
        )

    async def shutdown(self) -> None:
        await self._stop_all_proactive_tasks()

    def list(self, *, user_id: Optional[str] = None, is_admin: bool = False) -> List[dict]:
        items = []
        for deployment in self._deployments.values():
            if is_admin or deployment.created_by == user_id:
                items.append(self._serialize(deployment))
        return sorted(items, key=lambda item: (item.get("name", "").lower(), item.get("id", "")))

    def get(self, deployment_id: str) -> Optional[dict]:
        deployment = self._deployments.get(deployment_id)
        if deployment is None:
            return None
        return self._serialize(deployment)

    def get_config(self, deployment_id: str) -> Optional[AssistantDeploymentConfig]:
        return self._deployments.get(deployment_id)

    def find_for_channel(self, channel_id: str) -> Optional[AssistantDeploymentConfig]:
        for deployment in self._deployments.values():
            if deployment.enabled and channel_id in deployment.channel_ids:
                return deployment
        return None

    @staticmethod
    def _conversation_key(channel_id: str, sender_id: Optional[str], session_id: Optional[str] = None) -> str:
        sid = str(session_id or "").strip()
        if sid:
            return f"session:{channel_id}:{sid}"
        return f"channel:{channel_id}:{str(sender_id or '').strip()}"

    def _clear_conversation_handoffs_for_deployment(self, deployment_id: str) -> None:
        self._conversation_handoffs = {
            key: row
            for key, row in self._conversation_handoffs.items()
            if row.get("active_deployment_id") != deployment_id
            and row.get("primary_deployment_id") != deployment_id
            and row.get("source_deployment_id") != deployment_id
        }

    async def resolve_for_message(
        self,
        channel_id: str,
        content: str,
        *,
        sender_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> tuple[Optional[AssistantDeploymentConfig], Optional[AssistantDeploymentConfig], Optional[dict]]:
        primary = self.find_for_channel(channel_id)
        if primary is None:
            return None, None, None
        conversation_key = self._conversation_key(channel_id, sender_id, session_id)
        state = self._conversation_handoffs.get(conversation_key)
        current_owner = primary
        if state is not None:
            active_owner = self._deployments.get(str(state.get("active_deployment_id") or ""))
            if active_owner is None or not active_owner.enabled:
                self._conversation_handoffs.pop(conversation_key, None)
                state = None
            else:
                current_owner = active_owner

        handoff = await self._match_routing_rule(
            current_owner,
            content,
            primary=primary,
            sender_id=sender_id,
            session_id=session_id,
        )
        if handoff is not None:
            target = self._deployments.get(handoff["target_deployment_id"])
            if target is not None and target.enabled:
                handoff["target_name"] = target.name
                handoff["source_name"] = current_owner.name
                handoff["source_deployment_id"] = current_owner.id
                handoff["primary_deployment_id"] = primary.id
                handoff["conversation_key"] = conversation_key
                if target.id != current_owner.id:
                    handoff["event"] = "handoff"
                    if target.id == primary.id:
                        self._conversation_handoffs.pop(conversation_key, None)
                    else:
                        self._conversation_handoffs[conversation_key] = {
                            "primary_deployment_id": primary.id,
                            "active_deployment_id": target.id,
                            "source_deployment_id": current_owner.id,
                            "target_deployment_id": target.id,
                            "source_name": current_owner.name,
                            "target_name": target.name,
                            "reason": handoff.get("reason"),
                            "matched_keywords": list(handoff.get("matched_keywords") or []),
                            "selector_mode": handoff.get("selector_mode"),
                            "updated_at": _now_iso(),
                        }
                else:
                    handoff["event"] = "matched_current_owner"
                return primary, target, handoff

        if state is not None and current_owner.id != primary.id:
            source_id = str(state.get("source_deployment_id") or primary.id)
            source = self._deployments.get(source_id)
            return primary, current_owner, {
                "event": "active_handoff",
                "source_deployment_id": source_id,
                "source_name": source.name if source is not None else primary.name,
                "target_deployment_id": current_owner.id,
                "target_name": current_owner.name,
                "primary_deployment_id": primary.id,
                "conversation_key": conversation_key,
                "matched_keywords": list(state.get("matched_keywords") or []),
                "selector_mode": str(state.get("selector_mode") or current_owner.handoff_selector_mode or "hybrid"),
                "reason": str(state.get("reason") or "Conversation remains assigned to this specialist."),
            }
        return primary, primary, None

    def find_channel_conflicts(
        self,
        channel_ids: List[str],
        *,
        exclude_deployment_id: Optional[str] = None,
        created_by: Optional[str] = None,
        is_admin: bool = False,
    ) -> List[Dict[str, Any]]:
        selected = {str(channel_id).strip() for channel_id in channel_ids if str(channel_id).strip()}
        if not selected:
            return []
        conflicts: List[Dict[str, Any]] = []
        for deployment in self._deployments.values():
            if exclude_deployment_id and deployment.id == exclude_deployment_id:
                continue
            if not is_admin and created_by and deployment.created_by and deployment.created_by != created_by:
                continue
            for channel_id in deployment.channel_ids:
                if channel_id not in selected:
                    continue
                conflicts.append(
                    {
                        "channel_id": channel_id,
                        "existing_deployment_id": deployment.id,
                        "existing_deployment_name": deployment.name or deployment.id,
                        "existing_deployment_enabled": bool(deployment.enabled),
                    }
                )
        conflicts.sort(key=lambda row: (str(row.get("existing_deployment_name") or "").lower(), str(row.get("channel_id") or "")))
        return conflicts

    def add(self, config: AssistantDeploymentConfig) -> AssistantDeploymentConfig:
        config.channel_ids = self._normalize_channel_ids(config.channel_ids)
        config.toolkit_names = self._normalize_name_list(config.toolkit_names)
        config.skill_names = self._normalize_name_list(config.skill_names)
        config.handoff_selector_mode = self._normalize_handoff_selector_mode(config.handoff_selector_mode)
        config.handoff_selector_prompt = str(config.handoff_selector_prompt or "").strip()
        config.routing_rules = self._normalize_routing_rules(config.routing_rules)
        config.proactive_tasks = self._normalize_proactive_tasks(config.proactive_tasks)
        config.safety = self._normalize_safety(config.safety)
        config.profile = str(config.profile or "general").strip() or "general"
        config.linked_space_id = self._normalize_optional_text(config.linked_space_id)
        config.linked_space_title = self._normalize_optional_text(config.linked_space_title)
        config.linked_workflow_name = self._normalize_optional_text(config.linked_workflow_name)
        config.model_source = (config.model_source or "").strip() or None
        config.model_name = (config.model_name or "").strip() or None
        self._detach_channels_from_other_deployments(config.channel_ids, keep_id=config.id)
        self._touch(config, created=True)
        self._deployments[config.id] = config
        self._save()
        return config

    def update(self, deployment_id: str, updates: Dict[str, Any]) -> Optional[AssistantDeploymentConfig]:
        current = self._deployments.get(deployment_id)
        if current is None:
            return None
        payload = current.model_dump()
        payload.update({key: value for key, value in updates.items() if value is not None})
        if "channel_ids" in payload:
            payload["channel_ids"] = self._normalize_channel_ids(payload.get("channel_ids"))
        if "toolkit_names" in payload:
            payload["toolkit_names"] = self._normalize_name_list(payload.get("toolkit_names"))
        if "skill_names" in payload:
            payload["skill_names"] = self._normalize_name_list(payload.get("skill_names"))
        if "handoff_selector_mode" in payload:
            payload["handoff_selector_mode"] = self._normalize_handoff_selector_mode(payload.get("handoff_selector_mode"))
        if "handoff_selector_prompt" in payload:
            payload["handoff_selector_prompt"] = str(payload.get("handoff_selector_prompt") or "").strip()
        if "routing_rules" in payload:
            payload["routing_rules"] = self._normalize_routing_rules(payload.get("routing_rules"))
        if "proactive_tasks" in payload:
            payload["proactive_tasks"] = self._normalize_proactive_tasks(payload.get("proactive_tasks"))
        if "safety" in payload:
            payload["safety"] = self._normalize_safety(payload.get("safety"))
        if "profile" in payload:
            payload["profile"] = str(payload.get("profile") or "general").strip() or "general"
        if "linked_space_id" in payload:
            payload["linked_space_id"] = self._normalize_optional_text(payload.get("linked_space_id"))
        if "linked_space_title" in payload:
            payload["linked_space_title"] = self._normalize_optional_text(payload.get("linked_space_title"))
        if "linked_workflow_name" in payload:
            payload["linked_workflow_name"] = self._normalize_optional_text(payload.get("linked_workflow_name"))
        if "model_source" in payload:
            payload["model_source"] = (payload.get("model_source") or "").strip() or None
        if "model_name" in payload:
            payload["model_name"] = (payload.get("model_name") or "").strip() or None
        updated = AssistantDeploymentConfig(**payload)
        self._detach_channels_from_other_deployments(updated.channel_ids, keep_id=deployment_id)
        self._touch(updated)
        self._deployments[deployment_id] = updated
        self._save()
        return updated

    async def remove(self, deployment_id: str) -> bool:
        deployment = self._deployments.pop(deployment_id, None)
        if deployment is None:
            return False
        await self._stop_proactive_tasks(deployment_id)
        self._clear_conversation_handoffs_for_deployment(deployment_id)
        self._runtime_stats.pop(deployment_id, None)
        self._handoff_history = [
            row for row in self._handoff_history
            if row.get("source_deployment_id") != deployment_id and row.get("target_deployment_id") != deployment_id
        ]
        self._message_history = [
            row for row in self._message_history
            if row.get("deployment_id") != deployment_id
        ]
        self._endpoint_history = [
            row for row in self._endpoint_history
            if row.get("deployment_id") != deployment_id
        ]
        self._proactive_history = [
            row for row in self._proactive_history
            if row.get("deployment_id") != deployment_id
        ]
        for task in deployment.proactive_tasks:
            self._proactive_runtime.pop(_proactive_key(deployment_id, task.id), None)
        self._pending_proactive_approvals = {
            approval_id: row
            for approval_id, row in self._pending_proactive_approvals.items()
            if row.get("deployment_id") != deployment_id
        }
        self._pending_tool_approvals = {
            approval_id: row
            for approval_id, row in self._pending_tool_approvals.items()
            if row.get("deployment_id") != deployment_id
        }
        self._approval_history = [
            row for row in self._approval_history
            if row.get("deployment_id") != deployment_id
        ]
        self._tool_approval_history = [
            row for row in self._tool_approval_history
            if row.get("deployment_id") != deployment_id
        ]
        self._save()
        return True

    async def start(self, deployment_id: str) -> Optional[dict]:
        deployment = self._deployments.get(deployment_id)
        if deployment is None:
            return None
        deployment.enabled = True
        self._touch(deployment)
        await self._sync_proactive_tasks(deployment)
        self._save()
        return self._serialize(deployment)

    async def stop(self, deployment_id: str) -> Optional[dict]:
        deployment = self._deployments.get(deployment_id)
        if deployment is None:
            return None
        deployment.enabled = False
        self._touch(deployment)
        self._clear_conversation_handoffs_for_deployment(deployment_id)
        await self._stop_proactive_tasks(deployment_id)
        self._save()
        return self._serialize(deployment)

    async def start_auto(self) -> None:
        for deployment in self._deployments.values():
            if deployment.enabled and deployment.auto_start:
                await self._sync_proactive_tasks(deployment)

    async def refresh_runtime(self, deployment_id: str) -> Optional[dict]:
        deployment = self._deployments.get(deployment_id)
        if deployment is None:
            return None
        if deployment.enabled:
            await self._sync_proactive_tasks(deployment)
        else:
            await self._stop_proactive_tasks(deployment_id)
        return self._serialize(deployment)

    async def run_proactive_tasks(self, deployment_id: str, task_id: Optional[str] = None) -> Optional[dict]:
        deployment = self._deployments.get(deployment_id)
        if deployment is None:
            return None
        tasks = [
            task
            for task in deployment.proactive_tasks
            if task.enabled and (task_id is None or task.id == task_id)
        ]
        if task_id and not tasks:
            raise KeyError(task_id)
        results = []
        for task in tasks:
            results.append(await self._run_proactive_task(deployment, task, reason="manual"))
        return {
            "deployment": self._serialize(deployment),
            "results": results,
        }

    def get_pending_approval(self, approval_id: str) -> Optional[Dict[str, Any]]:
        row = self._pending_proactive_approvals.get(approval_id)
        return dict(row) if row else None

    def get_pending_tool_approval(self, approval_id: str) -> Optional[Dict[str, Any]]:
        row = self._pending_tool_approvals.get(approval_id)
        return dict(row) if row else None

    async def approve_pending_proactive(self, approval_id: str) -> Optional[Dict[str, Any]]:
        approval = self._pending_proactive_approvals.pop(approval_id, None)
        if approval is None:
            return None
        delivered, error, channel_id, recipient_id = await self._deliver_saved_approval(approval)
        now = _now_iso()
        approval["status"] = "approved" if delivered and not error else "approval_error"
        approval["resolved_at"] = now
        approval["delivery_error"] = error
        approval["delivered"] = delivered
        approval["channel_id"] = channel_id or approval.get("channel_id")
        approval["recipient_id"] = recipient_id or approval.get("recipient_id")
        self._approval_history.append(dict(approval))
        self._approval_history = self._approval_history[-100:]

        deployment = self._deployments.get(approval["deployment_id"])
        if deployment is not None:
            self._apply_approval_resolution(
                deployment.id,
                approval["task_id"],
                approval_id=approval_id,
                status=approval["status"],
                resolved_at=now,
                preview=approval.get("response_text", ""),
                error=error,
            )
        return approval

    async def reject_pending_proactive(self, approval_id: str) -> Optional[Dict[str, Any]]:
        approval = self._pending_proactive_approvals.pop(approval_id, None)
        if approval is None:
            return None
        now = _now_iso()
        approval["status"] = "rejected"
        approval["resolved_at"] = now
        approval["delivered"] = False
        self._approval_history.append(dict(approval))
        self._approval_history = self._approval_history[-100:]

        deployment = self._deployments.get(approval["deployment_id"])
        if deployment is not None:
            self._apply_approval_resolution(
                deployment.id,
                approval["task_id"],
                approval_id=approval_id,
                status="rejected",
                resolved_at=now,
                preview=approval.get("response_text", ""),
                error=None,
            )
        return approval

    def record_tool_approval_request(
        self,
        deployment_id: str,
        *,
        channel_id: str,
        sender_id: str,
        approval: Dict[str, Any],
        preview: str = "",
        routed_from: Optional[str] = None,
        handoff: Optional[dict] = None,
    ) -> Dict[str, Any]:
        now = _now_iso()
        stats = self._runtime_stats.setdefault(deployment_id, self._empty_runtime_stats())
        stats["message_count"] += 1
        stats["last_message_at"] = now
        stats["last_channel_id"] = channel_id
        stats["last_sender_id"] = sender_id
        stats["last_preview"] = preview[:240]
        stats["last_error"] = None
        stats["last_approval_id"] = approval.get("id")
        stats["last_approval_status"] = "pending"
        stats["last_approval_at"] = now
        stats["last_approval_kind"] = "tool"
        stats["last_tool_name"] = approval.get("tool_name")

        row = {
            "id": str(approval.get("id") or f"tool_approval_{uuid.uuid4().hex[:10]}"),
            "deployment_id": deployment_id,
            "session_id": str(approval.get("session_id") or ""),
            "channel_id": channel_id,
            "sender_id": sender_id,
            "tool_name": str(approval.get("tool_name") or "tool"),
            "tool_args": approval.get("tool_args") if isinstance(approval.get("tool_args"), dict) else None,
            "approval_type": str(approval.get("approval_type") or "required"),
            "pause_type": str(approval.get("pause_type") or "confirmation"),
            "created_at": str(approval.get("created_at") or now),
            "status": "pending",
            "preview": preview[:240],
            "source_deployment_id": routed_from,
            "reason": (handoff or {}).get("reason"),
            "selector_mode": (handoff or {}).get("selector_mode"),
        }
        self._pending_tool_approvals[row["id"]] = row
        stats["pending_tool_approval_count"] = len([
            item for item in self._pending_tool_approvals.values()
            if item.get("deployment_id") == deployment_id
        ])
        stats["pending_approval_count"] = stats["pending_tool_approval_count"] + len([
            item for item in self._pending_proactive_approvals.values()
            if item.get("deployment_id") == deployment_id
        ])
        if routed_from:
            source_stats = self._runtime_stats.setdefault(routed_from, self._empty_runtime_stats())
            source_stats["message_count"] += 1
            source_stats["last_message_at"] = now
            source_stats["last_channel_id"] = channel_id
            source_stats["last_sender_id"] = sender_id
            source_stats["last_handoff_at"] = now
            source_stats["last_handoff_from"] = None
            source_stats["last_handoff_target"] = deployment_id
            source_stats["last_handoff_reason"] = (handoff or {}).get("reason")
            source_stats["last_preview"] = preview[:240]
            stats["last_handoff_at"] = now
            stats["last_handoff_from"] = routed_from
            stats["last_handoff_target"] = None
            stats["last_handoff_reason"] = (handoff or {}).get("reason")
            self._handoff_history.append(
                {
                    "timestamp": now,
                    "source_deployment_id": routed_from,
                    "target_deployment_id": deployment_id,
                    "channel_id": channel_id,
                    "sender_id": sender_id,
                    "reason": (handoff or {}).get("reason"),
                    "matched_keywords": list((handoff or {}).get("matched_keywords") or []),
                    "selector_mode": (handoff or {}).get("selector_mode"),
                }
            )
            self._handoff_history = self._handoff_history[-50:]
        return dict(row)

    async def approve_pending_tool_approval(self, approval_id: str) -> Optional[Dict[str, Any]]:
        approval = self._pending_tool_approvals.get(approval_id)
        if approval is None:
            return None
        if self._channel_pool is None or not hasattr(self._channel_pool, "resolve_pending_tool_approval"):
            return {"error": "Assistant runtime is not available."}

        result = await self._channel_pool.resolve_pending_tool_approval(approval_id, approved=True)
        if result is None:
            return None
        if result.get("error"):
            return result

        self._pending_tool_approvals.pop(approval_id, None)
        now = _now_iso()
        response_text = str(result.get("response") or "")
        delivered = False
        delivery_error = None
        if response_text and not result.get("paused"):
            delivered, delivery_error = await self._deliver_tool_response(approval, response_text)
        history_row = {
            **approval,
            "status": "approved",
            "resolved_at": now,
            "response_text": response_text,
            "delivered": delivered,
            "delivery_error": delivery_error,
        }
        self._tool_approval_history.append(history_row)
        self._tool_approval_history = self._tool_approval_history[-100:]

        deployment_id = str(approval.get("deployment_id") or "")
        self._apply_tool_approval_resolution(
            deployment_id,
            approval_id=approval_id,
            status="approved",
            resolved_at=now,
            preview=response_text or str(approval.get("preview") or ""),
            error=delivery_error,
            tool_name=str(approval.get("tool_name") or ""),
        )
        if result.get("pending_tool_approval") and deployment_id:
            pending_next = dict(result["pending_tool_approval"])
            self.record_tool_approval_request(
                deployment_id,
                channel_id=str(approval.get("channel_id") or ""),
                sender_id=str(approval.get("sender_id") or ""),
                approval=pending_next,
                preview=response_text or str(approval.get("preview") or ""),
            )
        return history_row

    async def reject_pending_tool_approval(self, approval_id: str) -> Optional[Dict[str, Any]]:
        approval = self._pending_tool_approvals.get(approval_id)
        if approval is None:
            return None
        if self._channel_pool is None or not hasattr(self._channel_pool, "resolve_pending_tool_approval"):
            return {"error": "Assistant runtime is not available."}

        result = await self._channel_pool.resolve_pending_tool_approval(approval_id, approved=False)
        if result is None:
            return None
        if result.get("error"):
            return result

        self._pending_tool_approvals.pop(approval_id, None)
        now = _now_iso()
        response_text = str(result.get("response") or "")
        delivered = False
        delivery_error = None
        if response_text and not result.get("paused"):
            delivered, delivery_error = await self._deliver_tool_response(approval, response_text)
        history_row = {
            **approval,
            "status": "rejected",
            "resolved_at": now,
            "response_text": response_text,
            "delivered": delivered,
            "delivery_error": delivery_error,
        }
        self._tool_approval_history.append(history_row)
        self._tool_approval_history = self._tool_approval_history[-100:]

        deployment_id = str(approval.get("deployment_id") or "")
        self._apply_tool_approval_resolution(
            deployment_id,
            approval_id=approval_id,
            status="rejected",
            resolved_at=now,
            preview=response_text or str(approval.get("preview") or ""),
            error=delivery_error,
            tool_name=str(approval.get("tool_name") or ""),
        )
        if result.get("pending_tool_approval") and deployment_id:
            pending_next = dict(result["pending_tool_approval"])
            self.record_tool_approval_request(
                deployment_id,
                channel_id=str(approval.get("channel_id") or ""),
                sender_id=str(approval.get("sender_id") or ""),
                approval=pending_next,
                preview=response_text or str(approval.get("preview") or ""),
            )
        return history_row

    def _touch(self, config: AssistantDeploymentConfig, *, created: bool = False) -> None:
        now = _now_iso()
        if created and not config.created_at:
            config.created_at = now
        config.updated_at = now

    @staticmethod
    def _normalize_channel_ids(channel_ids: Optional[List[str]]) -> List[str]:
        seen = set()
        normalized: List[str] = []
        for channel_id in channel_ids or []:
            value = str(channel_id or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

    @staticmethod
    def _normalize_name_list(items: Optional[List[str]]) -> List[str]:
        seen = set()
        normalized: List[str] = []
        for item in items or []:
            value = str(item or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

    @staticmethod
    def _normalize_optional_text(value: Any) -> Optional[str]:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _normalize_handoff_selector_mode(value: Any) -> str:
        mode = str(value or "hybrid").strip().lower() or "hybrid"
        if mode not in _HANDOFF_SELECTOR_MODES:
            mode = "hybrid"
        return mode

    @staticmethod
    def _normalize_routing_rules(rules: Optional[List[Any]]) -> List[AssistantRoutingRule]:
        normalized: List[AssistantRoutingRule] = []
        seen_ids = set()
        for raw in rules or []:
            if raw is None:
                continue
            rule = raw if isinstance(raw, AssistantRoutingRule) else AssistantRoutingRule(**raw)
            rule.name = str(rule.name or "").strip()
            rule.target_deployment_id = str(rule.target_deployment_id or "").strip()
            rule.keywords = AssistantDeploymentManager._normalize_name_list(rule.keywords)
            if not rule.target_deployment_id:
                continue
            if rule.id in seen_ids:
                rule.id = f"route_{uuid.uuid4().hex[:8]}"
            seen_ids.add(rule.id)
            normalized.append(rule)
        return normalized

    @staticmethod
    def _normalize_proactive_tasks(tasks: Optional[List[Any]]) -> List[AssistantProactiveTask]:
        normalized: List[AssistantProactiveTask] = []
        seen_ids = set()
        for raw in tasks or []:
            if raw is None:
                continue
            task = raw if isinstance(raw, AssistantProactiveTask) else AssistantProactiveTask(**raw)
            task.name = str(task.name or "").strip()
            task.prompt = str(task.prompt or "").strip()
            task.channel_id = (task.channel_id or "").strip() or None
            task.recipient_id = (task.recipient_id or "").strip() or None
            task.trigger_kind = str(task.trigger_kind or "timer").strip().lower() or "timer"
            if task.trigger is None:
                trigger: Dict[str, Any] = {}
            elif isinstance(task.trigger, dict):
                trigger = dict(task.trigger)
            else:
                trigger = {"value": task.trigger}

            if task.trigger_kind == "timer":
                task.interval_sec = max(30, int(task.interval_sec or 0))
                normalized_trigger: Dict[str, Any] = {"immediate": bool(trigger.get("immediate", False))}
                if trigger.get("max_triggers") not in (None, ""):
                    normalized_trigger["max_triggers"] = int(trigger.get("max_triggers") or -1)
                task.trigger = normalized_trigger
            elif task.trigger_kind == "fswatch":
                task.interval_sec = max(0, int(task.interval_sec or 0))
                task.trigger = {
                    "path": str(trigger.get("path") or ".").strip() or ".",
                    "recursive": bool(trigger.get("recursive", True)),
                    "patterns": str(trigger.get("patterns") or "*").strip() or "*",
                    "events": str(trigger.get("events") or "created,modified,deleted,moved").strip() or "created,modified,deleted,moved",
                    "debounce_ms": max(0, int(trigger.get("debounce_ms") or 100)),
                }
            elif task.trigger_kind == "webhook":
                task.interval_sec = max(0, int(task.interval_sec or 0))
                normalized_trigger = {
                    "endpoint": str(trigger.get("endpoint") or "").strip(),
                    "methods": str(trigger.get("methods") or "POST").strip() or "POST",
                }
                if trigger.get("secret") not in (None, ""):
                    normalized_trigger["secret"] = str(trigger.get("secret") or "")
                task.trigger = normalized_trigger
            elif task.trigger_kind == "channel":
                task.interval_sec = max(0, int(task.interval_sec or 0))
                normalized_trigger = {}
                if trigger.get("channel_id") not in (None, ""):
                    normalized_trigger["channel_id"] = str(trigger.get("channel_id") or "").strip()
                if trigger.get("channel_types") not in (None, ""):
                    normalized_trigger["channel_types"] = str(trigger.get("channel_types") or "").strip()
                if trigger.get("sender_filter") not in (None, ""):
                    normalized_trigger["sender_filter"] = str(trigger.get("sender_filter") or "").strip()
                task.trigger = normalized_trigger or None
            elif task.trigger_kind == "browser":
                task.interval_sec = max(0, int(task.interval_sec or 0))
                normalized_trigger = {
                    "device_type": str(trigger.get("device_type") or "webcam").strip() or "webcam",
                    "mode": str(trigger.get("mode") or "event").strip() or "event",
                    "interval_ms": max(100, int(trigger.get("interval_ms") or 1000)),
                }
                if trigger.get("resolution") not in (None, ""):
                    normalized_trigger["resolution"] = str(trigger.get("resolution") or "").strip()
                if trigger.get("audio_format") not in (None, ""):
                    normalized_trigger["audio_format"] = str(trigger.get("audio_format") or "").strip()
                task.trigger = normalized_trigger
            else:
                task.interval_sec = max(0, int(task.interval_sec or 0))
                task.trigger = trigger or None
            if not task.name or not task.prompt:
                continue
            if task.id in seen_ids:
                task.id = f"proactive_{uuid.uuid4().hex[:8]}"
            seen_ids.add(task.id)
            normalized.append(task)
        return normalized

    @staticmethod
    def _normalize_safety(raw: Any) -> AssistantSafetyConfig:
        safety = raw if isinstance(raw, AssistantSafetyConfig) else AssistantSafetyConfig(**(raw or {}))
        mode = str(safety.proactive_delivery_mode or "auto").strip().lower()
        if mode not in {"auto", "approval"}:
            mode = "auto"
        safety.proactive_delivery_mode = mode
        tool_mode = str(safety.tool_execution_mode or "auto").strip().lower()
        if tool_mode not in {"auto", "approval"}:
            tool_mode = "auto"
        safety.tool_execution_mode = tool_mode
        return safety

    @staticmethod
    def _match_keyword_routing_rule(deployment: AssistantDeploymentConfig, content: str) -> Optional[dict]:
        text = str(content or "").lower()
        for rule in deployment.routing_rules:
            if not rule.enabled:
                continue
            if any(keyword.lower() in text for keyword in rule.keywords):
                matched = [keyword for keyword in rule.keywords if keyword.lower() in text]
                return {
                    "rule_id": rule.id,
                    "rule_name": rule.name or rule.target_deployment_id,
                    "target_deployment_id": rule.target_deployment_id,
                    "matched_keywords": matched,
                    "selector_mode": "keyword",
                    "reason": f"matched keyword(s): {', '.join(matched)}",
                }
        return None

    @staticmethod
    def _parse_selector_payload(text: Any) -> Optional[Dict[str, Any]]:
        raw = str(text or "").strip()
        if not raw:
            return None
        candidates = [raw]
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            candidates.append(raw[start:end + 1])
        for candidate in candidates:
            try:
                payload = json.loads(candidate)
            except Exception:
                continue
            if isinstance(payload, dict):
                return payload
        return None

    def _load_selector_defaults(self) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        console_config: Dict[str, Any] = {}
        try:
            import credentials as _creds

            config_path = getattr(self._channel_pool, "_config_path", None)
            if config_path:
                console_config = _creds.load_json(config_path)
        except Exception:
            console_config = {}
        return (
            dict(console_config.get("model") or {}),
            dict(console_config.get("options") or {}),
            normalize_assistant_memory_config(console_config.get("memory") or {}),
        )

    async def _match_workflow_routing_rule(
        self,
        deployment: AssistantDeploymentConfig,
        content: str,
        *,
        primary: AssistantDeploymentConfig,
        sender_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Optional[dict]:
        if self._channel_pool is None:
            return None
        routes = [rule for rule in deployment.routing_rules if rule.enabled]
        if not routes:
            return None
        model_cfg, options_cfg, memory_cfg = self._load_selector_defaults()
        route_rows: List[Dict[str, Any]] = []
        route_by_id: Dict[str, AssistantRoutingRule] = {}
        for rule in routes:
            route_by_id[rule.id] = rule
            target = self._deployments.get(rule.target_deployment_id)
            route_rows.append(
                {
                    "route_id": rule.id,
                    "route_name": rule.name or rule.target_deployment_id,
                    "target_deployment_id": rule.target_deployment_id,
                    "target_name": target.name if target is not None else None,
                    "keywords": list(rule.keywords or []),
                }
            )
        selector_request = {
            "message": str(content or ""),
            "sender_id": str(sender_id or "") or None,
            "session_id": str(session_id or "") or None,
            "primary_deployment": {"id": primary.id, "name": primary.name},
            "current_owner": {"id": deployment.id, "name": deployment.name, "profile": deployment.profile},
            "available_routes": route_rows,
        }
        extra_instructions = [
            "[Deployment Handoff Selector]",
            "Choose at most one route for this incoming message.",
            "Return ONLY compact JSON.",
            'Use {"route_id":"stay","reason":"...","matched_keywords":[]} when the current owner should keep the conversation.',
            'Use {"route_id":"<route_id>","reason":"...","matched_keywords":["..."]} when one route should receive the conversation.',
            "matched_keywords may be empty when the handoff is semantic rather than literal keyword matching.",
        ]
        if deployment.handoff_selector_prompt.strip():
            extra_instructions.append(f"Selector guidance: {deployment.handoff_selector_prompt.strip()}")
        result = await run_workflow_backed_agent_turn(
            workflow_name=f"Handoff Selector: {deployment.name}",
            request=json.dumps(selector_request, ensure_ascii=False),
            model_source=deployment.model_source or model_cfg.get("source", "ollama"),
            model_name=deployment.model_name or model_cfg.get("name", "mistral"),
            toolkit_names=[],
            toolkit_args={},
            skill_names=[],
            options_config=options_cfg,
            extra_instructions=extra_instructions,
            sender_name=deployment.name,
            assistant_name=f"{deployment.name} Selector",
            assistant_description=f"Workflow-backed handoff selector for deployment {deployment.name}",
            base_url=str(getattr(self._channel_pool, "_base_url", "http://localhost:11360")),
            internal_token=str(getattr(self._channel_pool, "_internal_token", "") or ""),
            user_id=deployment.created_by or f"deployment:{deployment.id}",
            auth_token="",
            local_app=getattr(self._channel_pool, "_fastapi_app", None),
            channel_registry=getattr(self._channel_pool, "_channel_reg", None),
            deployment_id=deployment.id,
            memory_config=memory_cfg,
            memory_db_path=self._runtime_memory_db_path(f"deployment_{deployment.id}"),
        )
        payload = self._parse_selector_payload(result.get("response"))
        if not payload:
            return None
        decision = str(payload.get("decision") or "").strip().lower()
        route_id = str(payload.get("route_id") or "").strip()
        target_deployment_id = str(payload.get("target_deployment_id") or "").strip()
        if decision == "stay" or route_id.lower() == "stay" or target_deployment_id.lower() == "stay":
            return None
        selected_rule = route_by_id.get(route_id)
        if selected_rule is None and target_deployment_id:
            matches = [rule for rule in routes if rule.target_deployment_id == target_deployment_id]
            if len(matches) == 1:
                selected_rule = matches[0]
        if selected_rule is None:
            return None
        matched_keywords = self._normalize_name_list(payload.get("matched_keywords"))
        reason = str(payload.get("reason") or payload.get("rationale") or "").strip()
        if not reason:
            reason = f"selector chose route '{selected_rule.name or selected_rule.target_deployment_id}'"
        return {
            "rule_id": selected_rule.id,
            "rule_name": selected_rule.name or selected_rule.target_deployment_id,
            "target_deployment_id": selected_rule.target_deployment_id,
            "matched_keywords": matched_keywords,
            "selector_mode": "workflow",
            "reason": reason,
        }

    async def _match_routing_rule(
        self,
        deployment: AssistantDeploymentConfig,
        content: str,
        *,
        primary: AssistantDeploymentConfig,
        sender_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Optional[dict]:
        mode = self._normalize_handoff_selector_mode(deployment.handoff_selector_mode)
        if mode in {"keyword", "hybrid"}:
            matched = self._match_keyword_routing_rule(deployment, content)
            if matched is not None or mode == "keyword":
                return matched
        return await self._match_workflow_routing_rule(
            deployment,
            content,
            primary=primary,
            sender_id=sender_id,
            session_id=session_id,
        )

    def _empty_runtime_stats(self) -> Dict[str, Any]:
        return {
            "message_count": 0,
            "last_message_at": None,
            "last_error": None,
            "last_preview": "",
            "last_channel_id": None,
            "last_sender_id": None,
            "last_handoff_at": None,
            "last_handoff_from": None,
            "last_handoff_target": None,
            "last_handoff_reason": None,
            "proactive_run_count": 0,
            "last_proactive_at": None,
            "last_proactive_status": None,
            "last_proactive_task_id": None,
            "last_proactive_task_name": None,
            "last_proactive_preview": "",
            "last_proactive_error": None,
            "pending_approval_count": 0,
            "pending_tool_approval_count": 0,
            "last_approval_id": None,
            "last_approval_status": None,
            "last_approval_at": None,
            "last_approval_kind": None,
            "last_tool_name": None,
            "endpoint_call_count": 0,
            "last_endpoint_call_at": None,
            "last_endpoint_mode": None,
            "last_endpoint_target": None,
            "last_endpoint_kind": None,
            "last_endpoint_status": None,
            "last_endpoint_preview": "",
            "last_endpoint_error": None,
        }

    def _empty_proactive_runtime(self, task: AssistantProactiveTask) -> Dict[str, Any]:
        return {
            "task_id": task.id,
            "status": "stopped",
            "run_count": 0,
            "last_run_at": None,
            "last_status": None,
            "last_preview": "",
            "last_error": None,
            "last_delivery_channel_id": None,
            "last_delivery_recipient_id": None,
            "last_delivered_at": None,
            "last_approval_id": None,
            "next_run_at": None,
        }

    def _proactive_runtime_row(self, deployment_id: str, task: AssistantProactiveTask) -> Dict[str, Any]:
        key = _proactive_key(deployment_id, task.id)
        row = dict(self._proactive_runtime.get(key) or self._empty_proactive_runtime(task))
        deployment = self._deployments.get(deployment_id)
        if not task.enabled or deployment is None or not deployment.enabled:
            row["status"] = "stopped"
            row["next_run_at"] = None
        elif self._is_proactive_task_scheduled(key) and row.get("status") != "running":
            row["status"] = "scheduled"
        return row

    def _serialize_proactive_task(self, deployment_id: str, task: AssistantProactiveTask) -> Dict[str, Any]:
        data = task.model_dump()
        data["runtime"] = self._proactive_runtime_row(deployment_id, task)
        return data

    def record_message(
        self,
        deployment_id: str,
        *,
        channel_id: str,
        sender_id: str,
        status: str,
        preview: str = "",
        routed_from: Optional[str] = None,
        handoff: Optional[dict] = None,
    ) -> None:
        now = _now_iso()
        stats = self._runtime_stats.setdefault(deployment_id, self._empty_runtime_stats())
        stats["message_count"] += 1
        stats["last_message_at"] = now
        stats["last_channel_id"] = channel_id
        stats["last_sender_id"] = sender_id
        stats["last_preview"] = preview[:240]
        if status == "error":
            stats["last_error"] = preview[:240]
        elif status == "ok":
            stats["last_error"] = None
        message_event = {
            "id": f"activity_{uuid.uuid4().hex[:10]}",
            "timestamp": now,
            "deployment_id": deployment_id,
            "kind": "routed_message" if routed_from else "message",
            "status": status,
            "channel_id": channel_id,
            "sender_id": sender_id,
            "preview": preview[:240],
            "source_deployment_id": routed_from,
            "reason": (handoff or {}).get("reason"),
            "selector_mode": (handoff or {}).get("selector_mode"),
        }
        self._message_history.append(message_event)
        self._message_history = self._message_history[-200:]
        if routed_from:
            source_stats = self._runtime_stats.setdefault(routed_from, self._empty_runtime_stats())
            source_stats["message_count"] += 1
            source_stats["last_message_at"] = now
            source_stats["last_channel_id"] = channel_id
            source_stats["last_sender_id"] = sender_id
            source_stats["last_handoff_at"] = now
            source_stats["last_handoff_from"] = None
            source_stats["last_handoff_target"] = deployment_id
            source_stats["last_handoff_reason"] = (handoff or {}).get("reason")
            source_stats["last_preview"] = preview[:240]
            stats["last_handoff_at"] = now
            stats["last_handoff_from"] = routed_from
            stats["last_handoff_target"] = None
            stats["last_handoff_reason"] = (handoff or {}).get("reason")
            self._handoff_history.append(
                {
                    "timestamp": now,
                    "source_deployment_id": routed_from,
                    "target_deployment_id": deployment_id,
                    "channel_id": channel_id,
                    "sender_id": sender_id,
                    "reason": (handoff or {}).get("reason"),
                    "matched_keywords": list((handoff or {}).get("matched_keywords") or []),
                    "selector_mode": (handoff or {}).get("selector_mode"),
                }
            )
            self._handoff_history = self._handoff_history[-50:]
            self._message_history.append(
                {
                    "id": f"activity_{uuid.uuid4().hex[:10]}",
                    "timestamp": now,
                    "deployment_id": routed_from,
                    "kind": "handoff",
                    "status": "ok",
                    "channel_id": channel_id,
                    "sender_id": sender_id,
                    "preview": preview[:240],
                    "target_deployment_id": deployment_id,
                    "reason": (handoff or {}).get("reason"),
                    "selector_mode": (handoff or {}).get("selector_mode"),
                }
            )
            self._message_history = self._message_history[-200:]

    def record_endpoint_interaction(
        self,
        deployment_id: str,
        *,
        mode: str,
        endpoint_kind: str,
        endpoint_target: str,
        endpoint_name: Optional[str] = None,
        status: str,
        preview: str = "",
        error: Optional[str] = None,
        session_id: Optional[str] = None,
        remote_task_id: Optional[str] = None,
    ) -> None:
        now = _now_iso()
        stats = self._runtime_stats.setdefault(deployment_id, self._empty_runtime_stats())
        stats["endpoint_call_count"] = int(stats.get("endpoint_call_count") or 0) + 1
        stats["last_endpoint_call_at"] = now
        stats["last_endpoint_mode"] = mode
        stats["last_endpoint_target"] = endpoint_target
        stats["last_endpoint_kind"] = endpoint_kind
        stats["last_endpoint_status"] = status
        stats["last_endpoint_preview"] = preview[:240]
        stats["last_endpoint_error"] = error[:240] if error else None
        if status == "error" and error:
            stats["last_error"] = error[:240]

        self._endpoint_history.append(
            {
                "id": f"activity_{uuid.uuid4().hex[:10]}",
                "timestamp": now,
                "deployment_id": deployment_id,
                "kind": "endpoint_call",
                "status": status,
                "mode": mode,
                "endpoint_kind": endpoint_kind,
                "endpoint_target": endpoint_target,
                "endpoint_name": endpoint_name,
                "preview": preview[:240],
                "error": error[:240] if error else None,
                "session_id": session_id,
                "remote_task_id": remote_task_id,
            }
        )
        self._endpoint_history = self._endpoint_history[-200:]

    def _detach_channels_from_other_deployments(self, channel_ids: List[str], *, keep_id: str) -> None:
        if not channel_ids:
            return
        changed = False
        channel_set = set(channel_ids)
        for deployment in self._deployments.values():
            if deployment.id == keep_id:
                continue
            filtered = [channel_id for channel_id in deployment.channel_ids if channel_id not in channel_set]
            if filtered != deployment.channel_ids:
                deployment.channel_ids = filtered
                self._touch(deployment)
                changed = True
        if changed:
            self._save()

    def _channel_rows(self, channel_ids: List[str]) -> List[dict]:
        rows: List[dict] = []
        registry = self._channel_registry
        for channel_id in channel_ids:
            adapter = registry.get(channel_id) if registry else None
            if adapter is None:
                rows.append({"id": channel_id, "name": channel_id, "channel_type": "missing", "status": "missing"})
            else:
                rows.append(adapter.get_status())
        return rows

    def _status_for(self, deployment: AssistantDeploymentConfig) -> str:
        if not deployment.enabled:
            return "disabled"
        if not deployment.channel_ids:
            return "unbound"
        statuses = [str(row.get("status", "")).lower() for row in self._channel_rows(deployment.channel_ids)]
        if not statuses:
            return "stopped"
        if any(status in {"error", "missing"} for status in statuses):
            return "error"
        if all(status == "running" for status in statuses):
            return "running"
        if any(status == "running" for status in statuses):
            return "partial"
        return "stopped"

    def _serialize(self, deployment: AssistantDeploymentConfig) -> dict:
        data = deployment.model_dump()
        data["status"] = self._status_for(deployment)
        data["channels"] = self._channel_rows(deployment.channel_ids)
        data["runtime"] = dict(self._runtime_stats.get(deployment.id) or self._empty_runtime_stats())
        data["recent_messages"] = [
            row for row in self._message_history
            if row.get("deployment_id") == deployment.id
        ][-10:]
        data["recent_endpoint_calls"] = [
            row for row in self._endpoint_history
            if row.get("deployment_id") == deployment.id
        ][-10:]
        data["recent_handoffs"] = [
            row for row in self._handoff_history
            if row.get("source_deployment_id") == deployment.id or row.get("target_deployment_id") == deployment.id
        ][-10:]
        data["recent_proactive_runs"] = [
            row for row in self._proactive_history
            if row.get("deployment_id") == deployment.id
        ][-10:]
        data["pending_proactive_approvals"] = [
            dict(row)
            for row in self._pending_proactive_approvals.values()
            if row.get("deployment_id") == deployment.id
        ][-10:]
        data["pending_tool_approvals"] = [
            dict(row)
            for row in self._pending_tool_approvals.values()
            if row.get("deployment_id") == deployment.id
        ][-10:]
        recent_proactive_approvals = [
            row for row in self._approval_history
            if row.get("deployment_id") == deployment.id
        ][-10:]
        recent_tool_approvals = [
            row for row in self._tool_approval_history
            if row.get("deployment_id") == deployment.id
        ][-10:]
        data["recent_approvals"] = sorted(
            [*recent_proactive_approvals, *recent_tool_approvals],
            key=lambda row: str(row.get("resolved_at") or row.get("created_at") or ""),
        )[-10:]
        data["recent_tool_approvals"] = recent_tool_approvals
        data["runtime"]["pending_tool_approval_count"] = len(data["pending_tool_approvals"])
        data["runtime"]["pending_approval_count"] = len(data["pending_proactive_approvals"]) + len(data["pending_tool_approvals"])
        data["recent_activity"] = self._recent_activity_for(deployment.id)
        data["recent_failures"] = [
            row for row in data["recent_activity"]
            if str(row.get("status", "")).lower() in {"error", "approval_error", "rejected"}
        ][-6:]
        data["proactive_tasks"] = [
            self._serialize_proactive_task(deployment.id, task)
            for task in deployment.proactive_tasks
        ]
        return data

    def _recent_activity_for(self, deployment_id: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for item in self._message_history:
            if item.get("deployment_id") != deployment_id:
                continue
            kind = str(item.get("kind") or "message")
            if kind == "handoff":
                title = "Handoff sent"
                detail = f"Routed to {item.get('target_deployment_id') or 'specialist'}"
            elif kind == "routed_message":
                title = "Routed message handled"
                detail = f"Received from {item.get('source_deployment_id') or 'another deployment'}"
            else:
                title = "Inbound message"
                detail = f"Channel {item.get('channel_id') or '-'}"
            rows.append(
                {
                    "id": item.get("id"),
                    "timestamp": item.get("timestamp"),
                    "kind": kind,
                    "status": item.get("status"),
                    "title": title,
                    "detail": detail if not item.get("reason") else f"{detail} · {item.get('reason')}",
                    "preview": item.get("preview") or "",
                }
            )
        for item in self._proactive_history:
            if item.get("deployment_id") != deployment_id:
                continue
            delivery_bits = []
            if item.get("reason"):
                delivery_bits.append(str(item.get("reason")))
            if item.get("delivered"):
                delivery_bits.append("delivered")
            elif item.get("approval_id"):
                delivery_bits.append("awaiting approval")
            rows.append(
                {
                    "id": item.get("id"),
                    "timestamp": item.get("timestamp"),
                    "kind": "proactive_run",
                    "status": item.get("status"),
                    "title": f"Proactive task: {item.get('task_name') or 'task'}",
                    "detail": " · ".join(delivery_bits) or "run completed",
                    "preview": item.get("preview") or "",
                }
            )
        for item in self._endpoint_history:
            if item.get("deployment_id") != deployment_id:
                continue
            endpoint_label = item.get("endpoint_name") or item.get("endpoint_target") or "endpoint"
            detail = f"{item.get('mode') or 'consult'} -> {endpoint_label}"
            endpoint_kind = str(item.get("endpoint_kind") or "")
            if endpoint_kind:
                detail += f" ({endpoint_kind})"
            if item.get("remote_task_id"):
                detail += f" · task {item.get('remote_task_id')}"
            rows.append(
                {
                    "id": item.get("id"),
                    "timestamp": item.get("timestamp"),
                    "kind": "endpoint_call",
                    "status": item.get("status"),
                    "title": "Agent endpoint call",
                    "detail": detail,
                    "preview": item.get("preview") or item.get("error") or "",
                }
            )
        for item in self._pending_proactive_approvals.values():
            if item.get("deployment_id") != deployment_id:
                continue
            rows.append(
                {
                    "id": item.get("id"),
                    "timestamp": item.get("created_at"),
                    "kind": "approval_pending",
                    "status": "pending",
                    "title": f"Approval requested: {item.get('task_name') or 'task'}",
                    "detail": f"Awaiting delivery approval for {item.get('recipient_id') or item.get('channel_id') or 'configured recipient'}",
                    "preview": item.get("response_text") or "",
                }
            )
        for item in self._pending_tool_approvals.values():
            if item.get("deployment_id") != deployment_id:
                continue
            tool_name = item.get("tool_name") or "tool"
            detail = f"Awaiting operator approval for {tool_name}"
            if item.get("sender_id"):
                detail += f" · sender {item.get('sender_id')}"
            rows.append(
                {
                    "id": item.get("id"),
                    "timestamp": item.get("created_at"),
                    "kind": "tool_approval_pending",
                    "status": "pending",
                    "title": f"Tool approval requested: {tool_name}",
                    "detail": detail,
                    "preview": item.get("preview") or "",
                }
            )
        for item in self._approval_history:
            if item.get("deployment_id") != deployment_id:
                continue
            rows.append(
                {
                    "id": item.get("id"),
                    "timestamp": item.get("resolved_at") or item.get("created_at"),
                    "kind": "approval",
                    "status": item.get("status"),
                    "title": f"Approval {item.get('status') or 'resolved'}",
                    "detail": item.get("task_name") or "Proactive task",
                    "preview": item.get("response_text") or "",
                }
            )
        for item in self._tool_approval_history:
            if item.get("deployment_id") != deployment_id:
                continue
            rows.append(
                {
                    "id": item.get("id"),
                    "timestamp": item.get("resolved_at") or item.get("created_at"),
                    "kind": "tool_approval",
                    "status": item.get("status"),
                    "title": f"Tool approval {item.get('status') or 'resolved'}",
                    "detail": item.get("tool_name") or "Tool call",
                    "preview": item.get("response_text") or item.get("preview") or "",
                }
            )
        rows.sort(key=lambda item: str(item.get("timestamp") or ""))
        return rows[-16:]

    async def _sync_proactive_tasks(self, deployment: AssistantDeploymentConfig) -> None:
        await self._stop_proactive_tasks(
            deployment.id,
            keep_task_ids={task.id for task in deployment.proactive_tasks if task.enabled},
        )
        if not deployment.enabled or self._channel_pool is None:
            return
        for task in deployment.proactive_tasks:
            if not task.enabled:
                continue
            await self._start_proactive_task(deployment, task)

    async def _start_proactive_task(self, deployment: AssistantDeploymentConfig, task: AssistantProactiveTask) -> None:
        key = _proactive_key(deployment.id, task.id)
        existing_meta = self._proactive_execution_meta.get(key)
        if existing_meta and existing_meta.get("execution_id"):
            return
        existing = self._proactive_loops.get(key)
        if existing and not existing.done():
            return
        runtime = self._proactive_runtime.setdefault(key, self._empty_proactive_runtime(task))
        runtime["status"] = "scheduled"
        runtime["next_run_at"] = self._next_proactive_run_at(task)
        if self._proactive_engine is None or self._channel_pool is None:
            if str(task.trigger_kind or "timer").strip().lower() != "timer":
                self._mark_proactive_task_start_error(
                    deployment.id,
                    task,
                    "This proactive trigger requires the workflow-backed event runtime.",
                )
                return
            self._proactive_loops[key] = asyncio.create_task(self._proactive_loop(deployment.id, task.id))
            return

        try:
            meta = await self._start_proactive_workflow(deployment, task)
        except Exception as exc:
            log_print(f"Assistant deployment proactive task failed to start ({deployment.id}/{task.id}): {exc}")
            self._mark_proactive_task_start_error(deployment.id, task, str(exc))
            return
        self._proactive_execution_meta[key] = meta
        self._proactive_execution_index[str(meta["execution_id"])] = key

    async def _stop_proactive_tasks(
        self, deployment_id: str, *, keep_task_ids: Optional[set[str]] = None
    ) -> None:
        prefix = f"{deployment_id}:"
        execution_keys = [
            key for key in list(self._proactive_execution_meta.keys())
            if key.startswith(prefix) and (keep_task_ids is None or key.split(":", 1)[1] not in keep_task_ids)
        ]
        for key in execution_keys:
            meta = self._proactive_execution_meta.pop(key, None) or {}
            execution_id = str(meta.get("execution_id") or "")
            if execution_id and self._proactive_engine is not None:
                with contextlib.suppress(Exception):
                    await self._proactive_engine.cancel_execution(execution_id)
            if execution_id:
                self._proactive_execution_index.pop(execution_id, None)
            await self._unregister_proactive_sources(meta)
            runtime = self._proactive_runtime.get(key)
            if runtime is not None:
                runtime["status"] = "stopped"
                runtime["next_run_at"] = None

        keys = [
            key for key in list(self._proactive_loops.keys())
            if key.startswith(prefix) and (keep_task_ids is None or key.split(":", 1)[1] not in keep_task_ids)
        ]
        for key in keys:
            task = self._proactive_loops.pop(key, None)
            if task is None:
                continue
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            runtime = self._proactive_runtime.get(key)
            if runtime is not None:
                runtime["status"] = "stopped"
                runtime["next_run_at"] = None

    async def _stop_all_proactive_tasks(self) -> None:
        for key, meta in list(self._proactive_execution_meta.items()):
            execution_id = str(meta.get("execution_id") or "")
            if execution_id and self._proactive_engine is not None:
                with contextlib.suppress(Exception):
                    await self._proactive_engine.cancel_execution(execution_id)
            if execution_id:
                self._proactive_execution_index.pop(execution_id, None)
            await self._unregister_proactive_sources(meta)
            runtime = self._proactive_runtime.get(key)
            if runtime is not None:
                runtime["status"] = "stopped"
                runtime["next_run_at"] = None
        self._proactive_execution_meta.clear()

        for key, task in list(self._proactive_loops.items()):
            self._proactive_loops.pop(key, None)
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            runtime = self._proactive_runtime.get(key)
            if runtime is not None:
                runtime["status"] = "stopped"
                runtime["next_run_at"] = None

    def _next_proactive_run_at(self, task: AssistantProactiveTask) -> Optional[str]:
        if str(task.trigger_kind or "timer").strip().lower() == "timer":
            return (datetime.now() + timedelta(seconds=max(30, int(task.interval_sec or 0)))).isoformat()
        return None

    def _is_proactive_task_scheduled(self, key: str) -> bool:
        meta = self._proactive_execution_meta.get(key)
        if meta and meta.get("execution_id"):
            return True
        task = self._proactive_loops.get(key)
        return task is not None and not task.done()

    async def _unregister_proactive_sources(self, meta: Dict[str, Any]) -> None:
        source_ids = list(meta.get("source_ids") or [])
        if not source_ids:
            return
        try:
            from events import get_event_registry
            registry = get_event_registry()
        except Exception:
            return
        for source_id in source_ids:
            if not source_id:
                continue
            with contextlib.suppress(Exception):
                await registry.unregister(str(source_id))

    async def _start_proactive_workflow(
        self,
        deployment: AssistantDeploymentConfig,
        task: AssistantProactiveTask,
    ) -> Dict[str, Any]:
        if self._proactive_engine is None or self._channel_pool is None:
            raise RuntimeError("Proactive workflow engine is not available")
        import credentials as _creds

        console_config = _creds.load_json(getattr(self._channel_pool, "_config_path"))
        model_cfg = dict(console_config.get("model") or {})
        options_cfg = dict(console_config.get("options") or {})
        toolkit_names = list(
            deployment.toolkit_names
            or console_config.get("toolkits")
            or ["console_toolkit"]
        )
        if getattr(self._channel_pool, "_ws_mgr", None) and "console_toolkit" not in toolkit_names:
            toolkit_names = ["console_toolkit"] + list(toolkit_names)

        source_id = _proactive_source_id(deployment.id, task.id)
        trigger_config = {"source_id": source_id, **dict(task.trigger or {})}
        built = build_assistant_proactive_workflow(
            deployment_name=deployment.name,
            deployment_profile=deployment.profile,
            deployment_description=deployment.description or "",
            deployment_instructions=deployment.instructions or "",
            task_name=task.name,
            task_prompt=task.prompt,
            task_interval_sec=max(30, int(task.interval_sec or 0)),
            model_source=deployment.model_source or model_cfg.get("source", "ollama"),
            model_name=deployment.model_name or model_cfg.get("name", "mistral"),
            toolkit_names=toolkit_names,
            toolkit_args={},
            skill_names=list(deployment.skill_names or []),
            options_config=options_cfg,
            memory_config=normalize_assistant_memory_config(console_config.get("memory") or {}),
            memory_db_path=self._runtime_memory_db_path(f"deployment_{deployment.id}"),
            trigger_kind=str(task.trigger_kind or "timer"),
            trigger_config=trigger_config,
        )
        payload = bind_runtime_toolkits_to_workflow(
            built["workflow"],
            base_url=str(getattr(self._channel_pool, "_base_url", "http://localhost:11360")),
            internal_token=str(getattr(self._channel_pool, "_internal_token", "") or ""),
            user_id=deployment.created_by or f"deployment:{deployment.id}",
            auth_token="",
            local_app=getattr(self._channel_pool, "_fastapi_app", None),
            channel_registry=getattr(self._channel_pool, "_channel_reg", None),
            deployment_id=deployment.id,
        )
        workflow = workflow_from_payload(payload)
        if workflow.options is None:
            workflow.options = {"name": f"Proactive Runtime: {deployment.name} / {task.name}"}
        backend = build_backend(workflow, skill_mgr=self._skill_mgr)
        execution_id = await self._proactive_engine.start_workflow(workflow, backend)
        return {
            "execution_id": execution_id,
            "deployment_id": deployment.id,
            "task_id": task.id,
            "task_name": task.name,
            "response_node_index": int(built["response_node_index"]),
            "source_ids": list(built.get("source_ids") or []),
            "workflow_name": str((workflow.options or {}).name if hasattr((workflow.options or {}), "name") else (workflow.options.get("name") if isinstance(workflow.options, dict) else f"Proactive Runtime: {deployment.name} / {task.name}")),
            "trigger_kind": str(task.trigger_kind or "timer"),
            "reason": "interval" if str(task.trigger_kind or "timer") == "timer" else "trigger",
        }

    def _resolve_proactive_task(
        self, deployment_id: str, task_id: str
    ) -> tuple[Optional[AssistantDeploymentConfig], Optional[AssistantProactiveTask]]:
        deployment = self._deployments.get(deployment_id)
        if deployment is None:
            return None, None
        for task in deployment.proactive_tasks:
            if task.id == task_id:
                return deployment, task
        return deployment, None

    async def _proactive_loop(self, deployment_id: str, task_id: str) -> None:
        key = _proactive_key(deployment_id, task_id)
        try:
            while True:
                deployment, task = self._resolve_proactive_task(deployment_id, task_id)
                if deployment is None or task is None or not deployment.enabled or not task.enabled:
                    break
                wait_seconds = max(30, int(task.interval_sec or 0))
                runtime = self._proactive_runtime.setdefault(key, self._empty_proactive_runtime(task))
                runtime["status"] = "scheduled"
                runtime["next_run_at"] = (datetime.now() + timedelta(seconds=wait_seconds)).isoformat()
                await asyncio.sleep(wait_seconds)
                deployment, task = self._resolve_proactive_task(deployment_id, task_id)
                if deployment is None or task is None or not deployment.enabled or not task.enabled:
                    break
                await self._run_proactive_task(deployment, task, reason="interval")
        except asyncio.CancelledError:
            raise
        finally:
            runtime = self._proactive_runtime.get(key)
            if runtime is not None:
                runtime["status"] = "stopped"
                runtime["next_run_at"] = None
            self._proactive_loops.pop(key, None)

    async def _on_proactive_node_completed(self, event) -> None:
        execution_id = str(getattr(event, "execution_id", "") or "")
        key = self._proactive_execution_index.get(execution_id)
        if not key:
            return
        meta = self._proactive_execution_meta.get(key) or {}
        if str(getattr(event, "node_id", "") or "") != str(meta.get("response_node_index")):
            return
        deployment_id = str(meta.get("deployment_id") or "")
        task_id = str(meta.get("task_id") or "")
        deployment, task = self._resolve_proactive_task(deployment_id, task_id)
        if deployment is None or task is None or not deployment.enabled or not task.enabled:
            return
        data = getattr(event, "data", None) or {}
        outputs = data.get("outputs") if isinstance(data, dict) else {}
        preview = ""
        if isinstance(outputs, dict):
            preview = str(outputs.get("output", "") or "")
        await self._record_proactive_result(
            deployment=deployment,
            task=task,
            reason=str(meta.get("reason") or "trigger"),
            preview=preview,
            error=None,
            workflow_name=str(meta.get("workflow_name") or ""),
            engine_execution_id=execution_id,
        )

    async def _on_proactive_workflow_completed(self, event) -> None:
        execution_id = str(getattr(event, "execution_id", "") or "")
        key = self._proactive_execution_index.pop(execution_id, None)
        if not key:
            return
        meta = self._proactive_execution_meta.pop(key, None) or {}
        await self._unregister_proactive_sources(meta)
        runtime = self._proactive_runtime.get(key)
        if runtime is not None:
            runtime["status"] = "stopped"
            runtime["next_run_at"] = None

    async def _on_proactive_workflow_failed(self, event) -> None:
        execution_id = str(getattr(event, "execution_id", "") or "")
        key = self._proactive_execution_index.pop(execution_id, None)
        if not key:
            return
        meta = self._proactive_execution_meta.pop(key, None) or {}
        await self._unregister_proactive_sources(meta)
        deployment_id = str(meta.get("deployment_id") or "")
        task_id = str(meta.get("task_id") or "")
        deployment, task = self._resolve_proactive_task(deployment_id, task_id)
        if deployment is None or task is None:
            return
        await self._record_proactive_result(
            deployment=deployment,
            task=task,
            reason=str(meta.get("reason") or "trigger"),
            preview="",
            error=str(getattr(event, "error", "") or "Workflow failed"),
            workflow_name=str(meta.get("workflow_name") or ""),
            engine_execution_id=execution_id,
        )
        runtime = self._proactive_runtime.get(key)
        if runtime is not None:
            runtime["status"] = "error"
            runtime["next_run_at"] = None

    async def _on_proactive_workflow_cancelled(self, event) -> None:
        execution_id = str(getattr(event, "execution_id", "") or "")
        key = self._proactive_execution_index.pop(execution_id, None)
        if not key:
            return
        meta = self._proactive_execution_meta.pop(key, None) or {}
        await self._unregister_proactive_sources(meta)
        runtime = self._proactive_runtime.get(key)
        if runtime is not None:
            runtime["status"] = "stopped"
            runtime["next_run_at"] = None

    def _mark_proactive_task_start_error(
        self,
        deployment_id: str,
        task: AssistantProactiveTask,
        message: str,
    ) -> None:
        key = _proactive_key(deployment_id, task.id)
        runtime = self._proactive_runtime.setdefault(key, self._empty_proactive_runtime(task))
        runtime["status"] = "error"
        runtime["next_run_at"] = None
        runtime["last_error"] = str(message or "Unable to start proactive task")[:240]
        stats = self._runtime_stats.setdefault(deployment_id, self._empty_runtime_stats())
        stats["last_proactive_status"] = "error"
        stats["last_proactive_task_id"] = task.id
        stats["last_proactive_task_name"] = task.name
        stats["last_proactive_error"] = runtime["last_error"]

    async def _record_proactive_result(
        self,
        *,
        deployment: AssistantDeploymentConfig,
        task: AssistantProactiveTask,
        reason: str,
        preview: str,
        error: Optional[str],
        workflow_name: Optional[str],
        engine_execution_id: Optional[str],
    ) -> Dict[str, Any]:
        key = _proactive_key(deployment.id, task.id)
        runtime = self._proactive_runtime.setdefault(key, self._empty_proactive_runtime(task))
        stats = self._runtime_stats.setdefault(deployment.id, self._empty_runtime_stats())
        now = _now_iso()
        delivered = False
        pending_approval = False
        approval_id = None
        delivery_channel_id = None
        delivery_recipient_id = None

        if not error and task.send_response:
            if deployment.safety.proactive_delivery_mode == "approval":
                approval = self._create_pending_approval(
                    deployment=deployment,
                    task=task,
                    response_text=preview,
                    reason=reason,
                )
                approval_id = approval["id"]
                pending_approval = True
            else:
                delivered, delivery_error, delivery_channel_id, delivery_recipient_id = await self._deliver_proactive_response(
                    deployment,
                    task,
                    preview,
                )
                if delivery_error:
                    error = delivery_error

        runtime["run_count"] = int(runtime.get("run_count") or 0) + 1
        runtime["last_run_at"] = now
        runtime["last_status"] = "error" if error else ("pending_approval" if pending_approval else "ok")
        runtime["last_preview"] = preview[:240]
        runtime["last_error"] = error[:240] if error else None
        runtime["last_delivery_channel_id"] = delivery_channel_id
        runtime["last_delivery_recipient_id"] = delivery_recipient_id
        runtime["last_delivered_at"] = now if delivered else None
        runtime["last_approval_id"] = approval_id
        runtime["status"] = "scheduled" if self._is_proactive_task_scheduled(key) else "stopped"
        runtime["next_run_at"] = self._next_proactive_run_at(task) if self._is_proactive_task_scheduled(key) else None

        stats["proactive_run_count"] = int(stats.get("proactive_run_count") or 0) + 1
        stats["last_proactive_at"] = now
        stats["last_proactive_status"] = "error" if error else ("pending_approval" if pending_approval else "ok")
        stats["last_proactive_task_id"] = task.id
        stats["last_proactive_task_name"] = task.name
        stats["last_proactive_preview"] = preview[:240]
        stats["last_proactive_error"] = error[:240] if error else None
        stats["last_approval_id"] = approval_id
        stats["last_approval_status"] = "pending" if pending_approval else None
        stats["last_approval_at"] = now if pending_approval else stats.get("last_approval_at")
        stats["pending_approval_count"] = len([
            row for row in self._pending_proactive_approvals.values()
            if row.get("deployment_id") == deployment.id
        ])

        event = {
            "timestamp": now,
            "deployment_id": deployment.id,
            "task_id": task.id,
            "task_name": task.name,
            "trigger_kind": str(task.trigger_kind or "timer"),
            "reason": reason,
            "status": "error" if error else ("pending_approval" if pending_approval else "ok"),
            "preview": preview[:240],
            "error": error[:240] if error else None,
            "delivered": delivered,
            "approval_id": approval_id,
            "channel_id": delivery_channel_id,
            "recipient_id": delivery_recipient_id,
            "workflow_backed": True,
            "workflow_name": workflow_name,
            "engine_execution_id": engine_execution_id,
        }
        self._proactive_history.append(event)
        self._proactive_history = self._proactive_history[-100:]
        return event

    async def _run_proactive_task(
        self, deployment: AssistantDeploymentConfig, task: AssistantProactiveTask, *, reason: str
    ) -> Dict[str, Any]:
        key = _proactive_key(deployment.id, task.id)
        runtime = self._proactive_runtime.setdefault(key, self._empty_proactive_runtime(task))
        stats = self._runtime_stats.setdefault(deployment.id, self._empty_runtime_stats())
        runtime["status"] = "running"
        runtime["next_run_at"] = None
        now = _now_iso()

        extra_instructions = [
            (
                "[Assistant Deployment]\n"
                f"Name: {deployment.name}\n"
                f"Profile: {deployment.profile}\n"
                f"Description: {deployment.description or '(none)'}\n"
                f"Instructions: {deployment.instructions or '(none)'}"
            ),
            (
                "[Proactive Task]\n"
                f"Task: {task.name}\n"
                f"Reason: {reason}\n"
                f"Current time: {now}\n"
                "This is a deployment-triggered proactive run. Be concise, actionable, and avoid asking the user to restate the task."
            ),
        ]

        preview = ""
        error = None

        result: Dict[str, Any] = {}
        try:
            if self._channel_pool is None:
                raise RuntimeError("Assistant deployment pool is not available")
            import credentials as _creds

            console_config = _creds.load_json(getattr(self._channel_pool, "_config_path"))
            model_cfg = dict(console_config.get("model") or {})
            options_cfg = dict(console_config.get("options") or {})
            toolkit_names = list(
                deployment.toolkit_names
                or console_config.get("toolkits")
                or ["console_toolkit"]
            )
            if getattr(self._channel_pool, "_ws_mgr", None) and "console_toolkit" not in toolkit_names:
                toolkit_names = ["console_toolkit"] + list(toolkit_names)

            result = await run_workflow_backed_agent_turn(
                workflow_name=f"Deployment Proactive Task: {deployment.name}",
                request=task.prompt,
                model_source=deployment.model_source or model_cfg.get("source", "ollama"),
                model_name=deployment.model_name or model_cfg.get("name", "mistral"),
                toolkit_names=toolkit_names,
                toolkit_args={},
                skill_names=list(deployment.skill_names or []),
                options_config=options_cfg,
                extra_instructions=extra_instructions,
                sender_name=deployment.name,
                assistant_name=deployment.name,
                assistant_description=deployment.description or None,
                base_url=str(getattr(self._channel_pool, "_base_url", "http://localhost:11360")),
                internal_token=str(getattr(self._channel_pool, "_internal_token", "") or ""),
                user_id=deployment.created_by or f"deployment:{deployment.id}",
                auth_token="",
                local_app=getattr(self._channel_pool, "_fastapi_app", None),
                channel_registry=getattr(self._channel_pool, "_channel_reg", None),
                deployment_id=deployment.id,
                memory_config=normalize_assistant_memory_config(console_config.get("memory") or {}),
                memory_db_path=self._runtime_memory_db_path(f"deployment_{deployment.id}"),
            )
            if result.get("error"):
                raise RuntimeError(str(result.get("error")))
            preview = str(result.get("response", "") or "")
        except Exception as exc:
            error = str(exc)
            preview = error
        return await self._record_proactive_result(
            deployment=deployment,
            task=task,
            reason=reason,
            preview=preview,
            error=error,
            workflow_name=result.get("workflow_name") if isinstance(result, dict) else None,
            engine_execution_id=result.get("engine_execution_id") if isinstance(result, dict) else None,
        )

    async def _deliver_proactive_response(
        self,
        deployment: AssistantDeploymentConfig,
        task: AssistantProactiveTask,
        text: str,
    ) -> tuple[bool, Optional[str], Optional[str], Optional[str]]:
        if not text.strip():
            return False, None, None, None
        registry = self._channel_registry
        if registry is None:
            return False, "Channel registry is not available", None, None
        channel_id = task.channel_id or (deployment.channel_ids[0] if deployment.channel_ids else None)
        if not channel_id:
            return False, "No channel available for proactive delivery", None, None
        adapter = registry.get(channel_id)
        if adapter is None:
            return False, f"Channel '{channel_id}' is not available", channel_id, None
        recipient_id = (
            task.recipient_id
            or getattr(adapter.config, "session_id", None)
            or adapter.config.extras.get("default_chat_id")
            or adapter.config.extras.get("default_recipient_id")
        )
        if not recipient_id:
            return False, "No recipient configured for proactive delivery", channel_id, None
        status = getattr(adapter.status, "value", str(adapter.status))
        channel_type = str(getattr(adapter.config, "channel_type", "") or "").strip().lower()
        if str(status).lower() != "running" and channel_type not in {"webhook"}:
            return False, f"Channel '{channel_id}' is not running", channel_id, recipient_id
        try:
            sent = await adapter.send(recipient_id, text)
            if not sent:
                return False, "Channel adapter returned an unsent result", channel_id, recipient_id
            return True, None, channel_id, recipient_id
        except Exception as exc:
            return False, str(exc), channel_id, recipient_id

    def _create_pending_approval(
        self,
        *,
        deployment: AssistantDeploymentConfig,
        task: AssistantProactiveTask,
        response_text: str,
        reason: str,
    ) -> Dict[str, Any]:
        approval_id = f"approval_{uuid.uuid4().hex[:10]}"
        approval = {
            "id": approval_id,
            "deployment_id": deployment.id,
            "deployment_name": deployment.name,
            "task_id": task.id,
            "task_name": task.name,
            "created_at": _now_iso(),
            "status": "pending",
            "reason": reason,
            "response_text": response_text,
            "channel_id": task.channel_id or (deployment.channel_ids[0] if deployment.channel_ids else None),
            "recipient_id": task.recipient_id,
        }
        self._pending_proactive_approvals[approval_id] = approval
        return approval

    async def _deliver_saved_approval(
        self, approval: Dict[str, Any]
    ) -> tuple[bool, Optional[str], Optional[str], Optional[str]]:
        deployment = self._deployments.get(str(approval.get("deployment_id") or ""))
        if deployment is None:
            return False, "Deployment is no longer available", approval.get("channel_id"), approval.get("recipient_id")
        task = next((row for row in deployment.proactive_tasks if row.id == approval.get("task_id")), None)
        if task is None:
            return False, "Proactive task is no longer available", approval.get("channel_id"), approval.get("recipient_id")
        task = task.model_copy(update={
            "channel_id": approval.get("channel_id") or task.channel_id,
            "recipient_id": approval.get("recipient_id") or task.recipient_id,
        })
        return await self._deliver_proactive_response(deployment, task, str(approval.get("response_text") or ""))

    async def _deliver_tool_response(
        self,
        approval: Dict[str, Any],
        text: str,
    ) -> tuple[bool, Optional[str]]:
        if not text.strip():
            return False, None
        registry = self._channel_registry
        if registry is None:
            return False, "Channel registry is not available"
        channel_id = str(approval.get("channel_id") or "").strip()
        if not channel_id:
            return False, "No channel is linked to this approval"
        adapter = registry.get(channel_id)
        if adapter is None:
            return False, f"Channel '{channel_id}' is not available"
        recipient_id = str(approval.get("sender_id") or approval.get("recipient_id") or "").strip()
        if not recipient_id:
            return False, "No recipient is linked to this approval"
        status = getattr(adapter.status, "value", str(adapter.status))
        channel_type = str(getattr(adapter.config, "channel_type", "") or "").strip().lower()
        if str(status).lower() != "running" and channel_type not in {"webhook"}:
            return False, f"Channel '{channel_id}' is not running"
        try:
            sent = await adapter.send(recipient_id, text)
            if not sent:
                return False, "Channel adapter returned an unsent result"
            return True, None
        except Exception as exc:
            return False, str(exc)

    def _apply_approval_resolution(
        self,
        deployment_id: str,
        task_id: str,
        *,
        approval_id: str,
        status: str,
        resolved_at: str,
        preview: str,
        error: Optional[str],
    ) -> None:
        stats = self._runtime_stats.setdefault(deployment_id, self._empty_runtime_stats())
        stats["last_approval_id"] = approval_id
        stats["last_approval_status"] = status
        stats["last_approval_at"] = resolved_at
        stats["last_approval_kind"] = "proactive"
        stats["pending_approval_count"] = len([
            row for row in self._pending_proactive_approvals.values()
            if row.get("deployment_id") == deployment_id
        ]) + len([
            row for row in self._pending_tool_approvals.values()
            if row.get("deployment_id") == deployment_id
        ])
        stats["pending_tool_approval_count"] = len([
            row for row in self._pending_tool_approvals.values()
            if row.get("deployment_id") == deployment_id
        ])
        stats["last_proactive_status"] = status
        stats["last_proactive_preview"] = preview[:240]
        stats["last_proactive_error"] = error[:240] if error else None

        key = _proactive_key(deployment_id, task_id)
        runtime = self._proactive_runtime.get(key)
        if runtime is not None:
            runtime["last_status"] = status
            runtime["last_preview"] = preview[:240]
            runtime["last_error"] = error[:240] if error else None
            runtime["last_approval_id"] = approval_id

    def _apply_tool_approval_resolution(
        self,
        deployment_id: str,
        *,
        approval_id: str,
        status: str,
        resolved_at: str,
        preview: str,
        error: Optional[str],
        tool_name: str,
    ) -> None:
        stats = self._runtime_stats.setdefault(deployment_id, self._empty_runtime_stats())
        stats["last_approval_id"] = approval_id
        stats["last_approval_status"] = status
        stats["last_approval_at"] = resolved_at
        stats["last_approval_kind"] = "tool"
        stats["last_tool_name"] = tool_name[:120] if tool_name else None
        stats["last_preview"] = preview[:240]
        if error:
            stats["last_error"] = error[:240]
        stats["pending_tool_approval_count"] = len([
            row for row in self._pending_tool_approvals.values()
            if row.get("deployment_id") == deployment_id
        ])
        stats["pending_approval_count"] = stats["pending_tool_approval_count"] + len([
            row for row in self._pending_proactive_approvals.values()
            if row.get("deployment_id") == deployment_id
        ])

    def _save(self) -> None:
        data = {deployment_id: deployment.model_dump() for deployment_id, deployment in self._deployments.items()}
        directory = os.path.dirname(self._config_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self._config_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)

    def _load(self) -> None:
        if not os.path.exists(self._config_path):
            return
        try:
            import credentials as _creds

            raw = _creds.load_json(self._config_path)
            for deployment_id, payload in raw.items():
                payload["id"] = deployment_id
                config = AssistantDeploymentConfig(**payload)
                config.channel_ids = self._normalize_channel_ids(config.channel_ids)
                config.toolkit_names = self._normalize_name_list(config.toolkit_names)
                config.skill_names = self._normalize_name_list(config.skill_names)
                config.handoff_selector_mode = self._normalize_handoff_selector_mode(config.handoff_selector_mode)
                config.handoff_selector_prompt = str(config.handoff_selector_prompt or "").strip()
                config.routing_rules = self._normalize_routing_rules(config.routing_rules)
                config.proactive_tasks = self._normalize_proactive_tasks(config.proactive_tasks)
                config.safety = self._normalize_safety(config.safety)
                config.profile = str(config.profile or "general").strip() or "general"
                config.linked_space_id = self._normalize_optional_text(config.linked_space_id)
                config.linked_space_title = self._normalize_optional_text(config.linked_space_title)
                config.linked_workflow_name = self._normalize_optional_text(config.linked_workflow_name)
                self._deployments[deployment_id] = config
        except Exception as exc:
            log_print(f"Failed to load assistant deployments: {exc}")


class AssistantDeploymentCreateRequest(BaseModel):
    name: str
    profile: str = "general"
    description: str = ""
    instructions: str = ""
    linked_space_id: Optional[str] = None
    linked_space_title: Optional[str] = None
    linked_workflow_name: Optional[str] = None
    model_source: Optional[str] = None
    model_name: Optional[str] = None
    toolkit_names: List[str] = Field(default_factory=list)
    skill_names: List[str] = Field(default_factory=list)
    channel_ids: List[str] = Field(default_factory=list)
    handoff_selector_mode: Literal["keyword", "hybrid", "workflow"] = "hybrid"
    handoff_selector_prompt: str = ""
    routing_rules: List[AssistantRoutingRule] = Field(default_factory=list)
    proactive_tasks: List[AssistantProactiveTask] = Field(default_factory=list)
    safety: AssistantSafetyConfig = Field(default_factory=AssistantSafetyConfig)
    enabled: bool = False
    auto_start: bool = False
    force_rebind_channels: bool = False


class AssistantDeploymentUpdateRequest(BaseModel):
    id: str
    name: Optional[str] = None
    profile: Optional[str] = None
    description: Optional[str] = None
    instructions: Optional[str] = None
    linked_space_id: Optional[str] = None
    linked_space_title: Optional[str] = None
    linked_workflow_name: Optional[str] = None
    model_source: Optional[str] = None
    model_name: Optional[str] = None
    toolkit_names: Optional[List[str]] = None
    skill_names: Optional[List[str]] = None
    channel_ids: Optional[List[str]] = None
    handoff_selector_mode: Optional[Literal["keyword", "hybrid", "workflow"]] = None
    handoff_selector_prompt: Optional[str] = None
    routing_rules: Optional[List[AssistantRoutingRule]] = None
    proactive_tasks: Optional[List[AssistantProactiveTask]] = None
    safety: Optional[AssistantSafetyConfig] = None
    enabled: Optional[bool] = None
    auto_start: Optional[bool] = None
    force_rebind_channels: bool = False


def setup_assistant_deployments_api(app: FastAPI, deployment_mgr: AssistantDeploymentManager, channel_registry=None) -> None:
    def _get_user(request: Request):
        user = getattr(request.state, "user", None)
        if not user:
            return None, False
        role = getattr(user, "role", "")
        return user.id, str(getattr(role, "value", role)).lower() == "admin"

    def _require_auth(request: Request):
        user = getattr(request.state, "user", None)
        if not user:
            raise HTTPException(401, "Authentication required")
        return user

    def _require_owner(request: Request, deployment: AssistantDeploymentConfig):
        user_id, is_admin = _get_user(request)
        if is_admin:
            return
        if not user_id or deployment.created_by != user_id:
            raise HTTPException(403, "Only the deployment owner or an admin can perform this action")

    def _require_channel_owner(request: Request, adapter) -> None:
        user_id, is_admin = _get_user(request)
        if is_admin:
            return
        owner = adapter.config.created_by
        if owner and owner != user_id:
            raise HTTPException(403, "Only the channel creator or an admin can perform this action")

    def _validate_channels(request: Request, channel_ids: List[str]) -> None:
        user_id, is_admin = _get_user(request)
        for channel_id in channel_ids:
            adapter = channel_registry.get(channel_id) if channel_registry else None
            if adapter is None:
                raise HTTPException(400, f"Unknown channel: {channel_id}")
            if is_admin:
                continue
            owner = adapter.config.created_by
            if owner and owner != user_id:
                raise HTTPException(403, f"Channel '{channel_id}' belongs to another user")

    def _validate_channel_bindings(
        request: Request,
        channel_ids: List[str],
        *,
        current_id: Optional[str] = None,
        force_rebind: bool = False,
    ) -> None:
        user_id, is_admin = _get_user(request)
        conflicts = deployment_mgr.find_channel_conflicts(
            channel_ids,
            exclude_deployment_id=current_id,
            created_by=user_id,
            is_admin=is_admin,
        )
        if conflicts and not force_rebind:
            raise HTTPException(
                409,
                {
                    "code": "channel_conflict",
                    "message": "One or more selected channels are already bound to another assistant deployment.",
                    "conflicts": conflicts,
                },
            )

    def _validate_routing(request: Request, routing_rules: List[AssistantRoutingRule], *, current_id: Optional[str] = None) -> None:
        user_id, is_admin = _get_user(request)
        normalized_rules = deployment_mgr._normalize_routing_rules(routing_rules)
        for rule in normalized_rules:
            if current_id and rule.target_deployment_id == current_id:
                raise HTTPException(400, "Routing rules cannot target the deployment itself")
            target = deployment_mgr.get_config(rule.target_deployment_id)
            if target is None:
                raise HTTPException(400, f"Unknown target deployment: {rule.target_deployment_id}")
            if is_admin:
                continue
            if target.created_by and target.created_by != user_id:
                raise HTTPException(403, f"Target deployment '{rule.target_deployment_id}' belongs to another user")

    def _validate_proactive_tasks(
        request: Request,
        deployment: Optional[AssistantDeploymentConfig],
        proactive_tasks: List[AssistantProactiveTask],
    ) -> None:
        user_id, is_admin = _get_user(request)
        allowed_channel_ids = set((deployment.channel_ids if deployment else []) or [])
        for task in proactive_tasks:
            trigger_kind = str(task.trigger_kind or "timer").strip().lower() or "timer"
            if trigger_kind not in _PROACTIVE_TRIGGER_KINDS:
                raise HTTPException(400, f"Proactive task '{task.name}' uses unsupported trigger kind '{trigger_kind}'")
            if trigger_kind == "timer" and task.interval_sec < 30:
                raise HTTPException(400, f"Proactive task '{task.name}' must use an interval of at least 30 seconds")
            trigger = task.trigger if isinstance(task.trigger, dict) else {}
            if trigger_kind == "channel":
                trigger_channel_id = str(trigger.get("channel_id") or "").strip()
                if trigger_channel_id:
                    adapter = channel_registry.get(trigger_channel_id) if channel_registry else None
                    if adapter is None:
                        raise HTTPException(400, f"Unknown proactive trigger channel: {trigger_channel_id}")
                    if not is_admin and adapter.config.created_by and adapter.config.created_by != user_id:
                        raise HTTPException(403, f"Trigger channel '{trigger_channel_id}' belongs to another user")
            if not task.channel_id:
                continue
            adapter = channel_registry.get(task.channel_id) if channel_registry else None
            if adapter is None:
                raise HTTPException(400, f"Unknown proactive task channel: {task.channel_id}")
            if not is_admin and adapter.config.created_by and adapter.config.created_by != user_id:
                raise HTTPException(403, f"Channel '{task.channel_id}' belongs to another user")
            if deployment and task.channel_id not in allowed_channel_ids:
                raise HTTPException(
                    400,
                    f"Proactive task '{task.name}' must target one of the deployment's bound channels or leave the channel empty",
                )

    def _visible_channels(request: Request) -> List[dict]:
        user_id, is_admin = _get_user(request)
        rows = channel_registry.list() if channel_registry else []
        if is_admin:
            return list(rows)
        return [
            row for row in rows
            if not row.get("created_by") or row.get("created_by") == user_id
        ]

    @app.post("/assistant-deployments/list")
    async def assistant_deployment_list(request: Request):
        user = _require_auth(request)
        _, is_admin = _get_user(request)
        return {"deployments": deployment_mgr.list(user_id=user.id, is_admin=is_admin)}

    @app.post("/assistant-deployments/network-workflow")
    async def assistant_deployment_network_workflow(request: Request):
        user = _require_auth(request)
        _, is_admin = _get_user(request)
        deployments = deployment_mgr.list(user_id=user.id, is_admin=is_admin)
        channels = _visible_channels(request)
        return build_assistant_network_workflow(deployments=deployments, channels=channels)

    @app.post("/assistant-deployments/network-workflow/apply")
    async def assistant_deployment_network_workflow_apply(payload: dict, request: Request):
        user = _require_auth(request)
        _, is_admin = _get_user(request)
        prune_missing = payload.get("prune_missing", True)
        if prune_missing is None:
            prune_missing = True
        prune_missing = bool(prune_missing)
        workflow = payload.get("workflow")
        if not isinstance(workflow, dict):
            raise HTTPException(status_code=400, detail="No valid workflow JSON")
        try:
            parsed = parse_assistant_network_workflow_import(workflow)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        warnings = list(parsed.get("warnings") or [])
        if prune_missing:
            warnings.append("Assistant network apply is authoritative: deployments and channels you own that are missing from the workflow will be removed.")
        else:
            warnings.append("Assistant network apply preserved existing deployments and channels that were not represented in the workflow.")

        existing_visible_channels = {
            str(row.get("id") or "").strip(): row
            for row in _visible_channels(request)
            if str(row.get("id") or "").strip()
        }
        visible_channel_ids = set(existing_visible_channels.keys())
        existing_visible_deployment_ids = {
            str(row.get("id") or "").strip()
            for row in deployment_mgr.list(user_id=user.id, is_admin=is_admin)
            if str(row.get("id") or "").strip()
        }
        creatable_channel_ids: set[str] = set()
        imported_channel_ids = {
            str(item.get("id") or "").strip()
            for item in parsed.get("channels") or []
            if str(item.get("id") or "").strip()
        }

        for channel_row in parsed.get("channels") or []:
            channel_id = str(channel_row.get("id") or "").strip()
            if not channel_id:
                continue
            channel_type = str(channel_row.get("channel_type") or "").strip().lower()
            if not channel_type:
                raise HTTPException(400, f"Channel '{channel_row.get('name') or channel_id}' is missing its channel_type.")
            existing_adapter = channel_registry.get(channel_id) if channel_registry else None
            if existing_adapter is not None:
                _require_channel_owner(request, existing_adapter)
                if channel_type != existing_adapter.config.channel_type:
                    raise HTTPException(
                        400,
                        f"Channel '{channel_id}' cannot change type from '{existing_adapter.config.channel_type}' to '{channel_type}'.",
                    )
                visible_channel_ids.add(channel_id)
                continue
            if channel_type not in {"webhook", "web"}:
                warnings.append(
                    f"Channel '{channel_row.get('name') or channel_id}' was not created because workflow-backed channel creation currently supports webhook and web channels without stored credentials."
                )
                continue
            visible_channel_ids.add(channel_id)
            creatable_channel_ids.add(channel_id)

        imported_deployment_ids = {str(item.get("id") or "").strip() for item in parsed.get("deployments") or [] if str(item.get("id") or "").strip()}

        for deployment_row in parsed.get("deployments") or []:
            deployment_id = str(deployment_row.get("id") or "").strip()
            if not deployment_id:
                continue
            existing = deployment_mgr.get_config(deployment_id)
            if existing is not None:
                _require_owner(request, existing)
            for channel_id in deployment_row.get("channel_ids") or []:
                if channel_id not in visible_channel_ids:
                    raise HTTPException(
                        400,
                        f"Deployment '{deployment_row.get('name') or deployment_id}' references unavailable channel '{channel_id}'.",
                    )
                if prune_missing and channel_id not in imported_channel_ids:
                    raise HTTPException(
                        400,
                        f"Deployment '{deployment_row.get('name') or deployment_id}' references channel '{channel_id}' but that channel is not represented in the workflow.",
                    )
            for route in deployment_row.get("routing_rules") or []:
                target_id = str(route.get("target_deployment_id") or "").strip()
                if not target_id:
                    raise HTTPException(400, f"Deployment '{deployment_row.get('name') or deployment_id}' has a route without a target deployment.")
                if target_id == deployment_id:
                    raise HTTPException(400, f"Deployment '{deployment_row.get('name') or deployment_id}' cannot route to itself.")
                target = deployment_mgr.get_config(target_id)
                if prune_missing and target_id not in imported_deployment_ids:
                    raise HTTPException(
                        400,
                        f"Route target deployment '{target_id}' must be represented in the workflow when authoritative apply is enabled.",
                    )
                if target is None and target_id not in imported_deployment_ids:
                    raise HTTPException(400, f"Unknown target deployment: {target_id}")
                if target is not None and not is_admin and target.created_by and target.created_by != user.id:
                    raise HTTPException(403, f"Target deployment '{target_id}' belongs to another user")
            conflicts = deployment_mgr.find_channel_conflicts(
                deployment_row.get("channel_ids") or [],
                exclude_deployment_id=deployment_id,
                created_by=user.id,
                is_admin=is_admin,
            )
            for conflict in conflicts:
                warnings.append(
                    f"Channel '{conflict['channel_id']}' was rebound from '{conflict['existing_deployment_name']}' to '{deployment_row.get('name') or deployment_id}'."
                )
            candidate = AssistantDeploymentConfig(
                id=deployment_id,
                name=str(deployment_row.get("name") or "").strip() or deployment_id,
                profile=str(deployment_row.get("profile") or "general").strip() or "general",
                description=str(deployment_row.get("description") or "").strip(),
                instructions=str(deployment_row.get("instructions") or "").strip(),
                linked_space_id=(str(deployment_row.get("linked_space_id") or "").strip() or None),
                linked_space_title=(str(deployment_row.get("linked_space_title") or "").strip() or None),
                linked_workflow_name=(str(deployment_row.get("linked_workflow_name") or "").strip() or None),
                model_source=(str(deployment_row.get("model_source") or "").strip() or None),
                model_name=(str(deployment_row.get("model_name") or "").strip() or None),
                toolkit_names=[str(name).strip() for name in deployment_row.get("toolkit_names") or [] if str(name).strip()],
                skill_names=[str(name).strip() for name in deployment_row.get("skill_names") or [] if str(name).strip()],
                channel_ids=[str(channel_id).strip() for channel_id in deployment_row.get("channel_ids") or [] if str(channel_id).strip()],
                handoff_selector_mode=str(deployment_row.get("handoff_selector_mode") or "hybrid").strip().lower() or "hybrid",
                handoff_selector_prompt=str(deployment_row.get("handoff_selector_prompt") or "").strip(),
                routing_rules=deployment_row.get("routing_rules") or [],
                proactive_tasks=deployment_row.get("proactive_tasks") or [],
                safety=deployment_row.get("safety") or {},
                enabled=bool(deployment_row.get("enabled")),
                auto_start=bool(deployment_row.get("auto_start")),
                created_by=(existing.created_by if existing and existing.created_by else user.id),
            )
            if prune_missing:
                for task in candidate.proactive_tasks:
                    if task.channel_id and task.channel_id not in imported_channel_ids:
                        raise HTTPException(
                            400,
                            f"Proactive task '{task.name}' references delivery channel '{task.channel_id}' but that channel is not represented in the workflow.",
                        )
                    trigger = task.trigger if isinstance(task.trigger, dict) else {}
                    if str(task.trigger_kind or "timer").strip().lower() == "channel":
                        trigger_channel_id = str(trigger.get("channel_id") or "").strip()
                        if trigger_channel_id and trigger_channel_id not in imported_channel_ids:
                            raise HTTPException(
                                400,
                                f"Proactive task '{task.name}' references trigger channel '{trigger_channel_id}' but that channel is not represented in the workflow.",
                            )
            _validate_proactive_tasks(request, candidate, candidate.proactive_tasks)

        created_channels: List[str] = []
        updated_channels: List[str] = []
        for channel_row in parsed.get("channels") or []:
            channel_id = str(channel_row.get("id") or "").strip()
            if not channel_id:
                continue
            channel_type = str(channel_row.get("channel_type") or "").strip().lower()
            existing_adapter = channel_registry.get(channel_id) if channel_registry else None
            if existing_adapter is not None:
                previous_status = existing_adapter.status
                config = ChannelConfig(
                    **{
                        **existing_adapter.config.model_dump(),
                        "id": channel_id,
                        "name": str(channel_row.get("name") or existing_adapter.config.name or channel_id).strip(),
                        "channel_type": channel_type,
                        "enabled": bool(channel_row.get("enabled", True)),
                        "auto_start": bool(channel_row.get("auto_start")),
                        "session_id": (str(channel_row.get("session_id") or "").strip() or None),
                        "allowed_users": [str(item).strip() for item in channel_row.get("allowed_users") or [] if str(item).strip()],
                        "created_by": existing_adapter.config.created_by,
                    }
                )
                await channel_registry.upsert_config(config)
                if not config.enabled and previous_status in {ChannelStatus.RUNNING, ChannelStatus.STARTING}:
                    await channel_registry.stop(channel_id)
                updated_channels.append(channel_id)
            else:
                if channel_id not in creatable_channel_ids:
                    continue
                config = ChannelConfig(
                    id=channel_id,
                    name=str(channel_row.get("name") or channel_id).strip(),
                    channel_type=channel_type,
                    enabled=bool(channel_row.get("enabled", True)),
                    auto_start=bool(channel_row.get("auto_start")),
                    session_id=(str(channel_row.get("session_id") or "").strip() or None),
                    allowed_users=[str(item).strip() for item in channel_row.get("allowed_users") or [] if str(item).strip()],
                    created_by=user.id,
                )
                await channel_registry.add(config)
                created_channels.append(channel_id)

        created_deployments: List[str] = []
        updated_deployments: List[str] = []
        for deployment_row in parsed.get("deployments") or []:
            deployment_id = str(deployment_row.get("id") or "").strip()
            if not deployment_id:
                continue
            existing = deployment_mgr.get_config(deployment_id)
            if existing is None:
                config = AssistantDeploymentConfig(
                    id=deployment_id,
                    name=str(deployment_row.get("name") or "").strip() or deployment_id,
                    profile=str(deployment_row.get("profile") or "general").strip() or "general",
                    description=str(deployment_row.get("description") or "").strip(),
                    instructions=str(deployment_row.get("instructions") or "").strip(),
                    linked_space_id=(str(deployment_row.get("linked_space_id") or "").strip() or None),
                    linked_space_title=(str(deployment_row.get("linked_space_title") or "").strip() or None),
                    linked_workflow_name=(str(deployment_row.get("linked_workflow_name") or "").strip() or None),
                    model_source=(str(deployment_row.get("model_source") or "").strip() or None),
                    model_name=(str(deployment_row.get("model_name") or "").strip() or None),
                    toolkit_names=[str(name).strip() for name in deployment_row.get("toolkit_names") or [] if str(name).strip()],
                    skill_names=[str(name).strip() for name in deployment_row.get("skill_names") or [] if str(name).strip()],
                    channel_ids=[str(channel_id).strip() for channel_id in deployment_row.get("channel_ids") or [] if str(channel_id).strip()],
                    handoff_selector_mode=str(deployment_row.get("handoff_selector_mode") or "hybrid").strip().lower() or "hybrid",
                    handoff_selector_prompt=str(deployment_row.get("handoff_selector_prompt") or "").strip(),
                    routing_rules=deployment_row.get("routing_rules") or [],
                    proactive_tasks=deployment_row.get("proactive_tasks") or [],
                    safety=deployment_row.get("safety") or {},
                    enabled=bool(deployment_row.get("enabled")),
                    auto_start=bool(deployment_row.get("auto_start")),
                    created_by=user.id,
                )
                deployment_mgr.add(config)
                created_deployments.append(deployment_id)
            else:
                deployment_mgr.update(
                    deployment_id,
                    {
                        "name": str(deployment_row.get("name") or "").strip() or deployment_id,
                        "profile": str(deployment_row.get("profile") or "general").strip() or "general",
                        "description": str(deployment_row.get("description") or "").strip(),
                        "instructions": str(deployment_row.get("instructions") or "").strip(),
                        "linked_space_id": (str(deployment_row.get("linked_space_id") or "").strip() or None),
                        "linked_space_title": (str(deployment_row.get("linked_space_title") or "").strip() or None),
                        "linked_workflow_name": (str(deployment_row.get("linked_workflow_name") or "").strip() or None),
                        "model_source": (str(deployment_row.get("model_source") or "").strip() or None),
                        "model_name": (str(deployment_row.get("model_name") or "").strip() or None),
                        "toolkit_names": [str(name).strip() for name in deployment_row.get("toolkit_names") or [] if str(name).strip()],
                        "skill_names": [str(name).strip() for name in deployment_row.get("skill_names") or [] if str(name).strip()],
                        "channel_ids": [str(channel_id).strip() for channel_id in deployment_row.get("channel_ids") or [] if str(channel_id).strip()],
                        "handoff_selector_mode": str(deployment_row.get("handoff_selector_mode") or "hybrid").strip().lower() or "hybrid",
                        "handoff_selector_prompt": str(deployment_row.get("handoff_selector_prompt") or "").strip(),
                        "routing_rules": deployment_row.get("routing_rules") or [],
                        "proactive_tasks": deployment_row.get("proactive_tasks") or [],
                        "safety": deployment_row.get("safety") or {},
                        "enabled": bool(deployment_row.get("enabled")),
                        "auto_start": bool(deployment_row.get("auto_start")),
                    },
                )
                updated_deployments.append(deployment_id)
            await deployment_mgr.refresh_runtime(deployment_id)

        deleted_deployments: List[str] = []
        deleted_channels: List[str] = []
        if prune_missing:
            for deployment_id in sorted(existing_visible_deployment_ids - imported_deployment_ids):
                existing = deployment_mgr.get_config(deployment_id)
                if existing is None:
                    continue
                _require_owner(request, existing)
                removed = await deployment_mgr.remove(deployment_id)
                if removed:
                    deleted_deployments.append(deployment_id)
            for channel_id in sorted(existing_visible_channels.keys() - imported_channel_ids):
                adapter = channel_registry.get(channel_id) if channel_registry else None
                if adapter is None:
                    continue
                _require_channel_owner(request, adapter)
                removed = await channel_registry.remove(channel_id)
                if removed:
                    deleted_channels.append(channel_id)

        return {
            "applied": True,
            "workflow_name": parsed.get("workflow_name") or "Assistant Deployment Network",
            "created_channels": created_channels,
            "updated_channels": updated_channels,
            "deleted_channels": deleted_channels,
            "created_deployments": created_deployments,
            "updated_deployments": updated_deployments,
            "deleted_deployments": deleted_deployments,
            "prune_missing": prune_missing,
            "warnings": warnings,
            "deployments": deployment_mgr.list(user_id=user.id, is_admin=is_admin),
        }

    @app.post("/assistant-deployments/get")
    async def assistant_deployment_get(request: Request):
        _require_auth(request)
        body = await request.json()
        deployment = deployment_mgr.get_config(str(body.get("id", "")).strip())
        if deployment is None:
            return {"error": "not found"}
        _require_owner(request, deployment)
        return deployment_mgr.get(deployment.id)

    @app.post("/assistant-deployments/create")
    async def assistant_deployment_create(request: Request, payload: AssistantDeploymentCreateRequest):
        user = _require_auth(request)
        _validate_channels(request, payload.channel_ids)
        _validate_channel_bindings(request, payload.channel_ids, force_rebind=payload.force_rebind_channels)
        config = AssistantDeploymentConfig(
            name=payload.name,
            profile=payload.profile,
            description=payload.description,
            instructions=payload.instructions,
            linked_space_id=(payload.linked_space_id or "").strip() or None,
            linked_space_title=(payload.linked_space_title or "").strip() or None,
            linked_workflow_name=(payload.linked_workflow_name or "").strip() or None,
            model_source=(payload.model_source or "").strip() or None,
            model_name=(payload.model_name or "").strip() or None,
            toolkit_names=[str(name).strip() for name in payload.toolkit_names if str(name).strip()],
            skill_names=[str(name).strip() for name in payload.skill_names if str(name).strip()],
            channel_ids=payload.channel_ids,
            handoff_selector_mode=str(payload.handoff_selector_mode or "hybrid").strip().lower() or "hybrid",
            handoff_selector_prompt=str(payload.handoff_selector_prompt or "").strip(),
            routing_rules=payload.routing_rules,
            proactive_tasks=payload.proactive_tasks,
            safety=payload.safety,
            enabled=payload.enabled,
            auto_start=payload.auto_start,
            created_by=user.id,
        )
        _validate_routing(request, config.routing_rules)
        _validate_proactive_tasks(request, config, config.proactive_tasks)
        deployment_mgr.add(config)
        return deployment_mgr.get(config.id)

    @app.post("/assistant-deployments/update")
    async def assistant_deployment_update(request: Request, payload: AssistantDeploymentUpdateRequest):
        _require_auth(request)
        current = deployment_mgr.get_config(payload.id)
        if current is None:
            return {"error": "not found"}
        _require_owner(request, current)
        updates = payload.model_dump(exclude={"id"}, exclude_unset=True)
        merged_channel_ids = updates.get("channel_ids", current.channel_ids)
        if "channel_ids" in updates:
            _validate_channels(request, updates["channel_ids"] or [])
            _validate_channel_bindings(
                request,
                updates["channel_ids"] or [],
                current_id=payload.id,
                force_rebind=payload.force_rebind_channels,
            )
        if "routing_rules" in updates:
            _validate_routing(request, updates["routing_rules"] or [], current_id=payload.id)
        if "proactive_tasks" in updates:
            candidate = AssistantDeploymentConfig(
                **{
                    **current.model_dump(),
                    **updates,
                    "channel_ids": merged_channel_ids,
                }
            )
            _validate_proactive_tasks(request, candidate, updates["proactive_tasks"] or [])
        updated = deployment_mgr.update(payload.id, updates)
        if updated is None:
            return {"error": "not found"}
        await deployment_mgr.refresh_runtime(payload.id)
        return deployment_mgr.get(updated.id)

    @app.post("/assistant-deployments/remove")
    async def assistant_deployment_remove(request: Request):
        _require_auth(request)
        body = await request.json()
        deployment_id = str(body.get("id", "")).strip()
        deployment = deployment_mgr.get_config(deployment_id)
        if deployment is None:
            return {"removed": False}
        _require_owner(request, deployment)
        removed = await deployment_mgr.remove(deployment_id)
        return {"removed": removed}

    @app.post("/assistant-deployments/start")
    async def assistant_deployment_start(request: Request):
        _require_auth(request)
        body = await request.json()
        deployment_id = str(body.get("id", "")).strip()
        deployment = deployment_mgr.get_config(deployment_id)
        if deployment is None:
            return {"error": "not found"}
        _require_owner(request, deployment)
        data = await deployment_mgr.start(deployment_id)
        return data or {"error": "not found"}

    @app.post("/assistant-deployments/stop")
    async def assistant_deployment_stop(request: Request):
        _require_auth(request)
        body = await request.json()
        deployment_id = str(body.get("id", "")).strip()
        deployment = deployment_mgr.get_config(deployment_id)
        if deployment is None:
            return {"error": "not found"}
        _require_owner(request, deployment)
        data = await deployment_mgr.stop(deployment_id)
        return data or {"error": "not found"}

    @app.post("/assistant-deployments/refresh-runtime")
    async def assistant_deployment_refresh_runtime(request: Request):
        _require_auth(request)
        body = await request.json()
        deployment_id = str(body.get("id", "")).strip()
        deployment = deployment_mgr.get_config(deployment_id)
        if deployment is None:
            return {"error": "not found"}
        _require_owner(request, deployment)
        data = await deployment_mgr.refresh_runtime(deployment_id)
        return data or {"error": "not found"}

    @app.post("/assistant-deployments/run-proactive")
    async def assistant_deployment_run_proactive(request: Request):
        _require_auth(request)
        body = await request.json()
        deployment_id = str(body.get("id", "")).strip()
        task_id = str(body.get("task_id", "")).strip() or None
        deployment = deployment_mgr.get_config(deployment_id)
        if deployment is None:
            return {"error": "not found"}
        _require_owner(request, deployment)
        try:
            data = await deployment_mgr.run_proactive_tasks(deployment_id, task_id=task_id)
        except KeyError:
            raise HTTPException(404, f"Unknown proactive task: {task_id}") from None
        return data or {"error": "not found"}

    @app.post("/assistant-deployments/approve-proactive")
    async def assistant_deployment_approve_proactive(request: Request):
        _require_auth(request)
        body = await request.json()
        approval_id = str(body.get("id", "")).strip()
        approval = deployment_mgr.get_pending_approval(approval_id)
        if approval is None:
            return {"error": "not found"}
        deployment = deployment_mgr.get_config(str(approval.get("deployment_id") or ""))
        if deployment is None:
            return {"error": "not found"}
        _require_owner(request, deployment)
        data = await deployment_mgr.approve_pending_proactive(approval_id)
        return data or {"error": "not found"}

    @app.post("/assistant-deployments/reject-proactive")
    async def assistant_deployment_reject_proactive(request: Request):
        _require_auth(request)
        body = await request.json()
        approval_id = str(body.get("id", "")).strip()
        approval = deployment_mgr.get_pending_approval(approval_id)
        if approval is None:
            return {"error": "not found"}
        deployment = deployment_mgr.get_config(str(approval.get("deployment_id") or ""))
        if deployment is None:
            return {"error": "not found"}
        _require_owner(request, deployment)
        data = await deployment_mgr.reject_pending_proactive(approval_id)
        return data or {"error": "not found"}

    @app.post("/assistant-deployments/approve-tool-call")
    async def assistant_deployment_approve_tool_call(request: Request):
        _require_auth(request)
        body = await request.json()
        approval_id = str(body.get("id", "")).strip()
        approval = deployment_mgr.get_pending_tool_approval(approval_id)
        if approval is None:
            return {"error": "not found"}
        deployment = deployment_mgr.get_config(str(approval.get("deployment_id") or ""))
        if deployment is None:
            return {"error": "not found"}
        _require_owner(request, deployment)
        data = await deployment_mgr.approve_pending_tool_approval(approval_id)
        return data or {"error": "not found"}

    @app.post("/assistant-deployments/reject-tool-call")
    async def assistant_deployment_reject_tool_call(request: Request):
        _require_auth(request)
        body = await request.json()
        approval_id = str(body.get("id", "")).strip()
        approval = deployment_mgr.get_pending_tool_approval(approval_id)
        if approval is None:
            return {"error": "not found"}
        deployment = deployment_mgr.get_config(str(approval.get("deployment_id") or ""))
        if deployment is None:
            return {"error": "not found"}
        _require_owner(request, deployment)
        data = await deployment_mgr.reject_pending_tool_approval(approval_id)
        return data or {"error": "not found"}
