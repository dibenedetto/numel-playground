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

from runtime_settings import get_runtime_settings
from utils import log_print


_CONFIG_PATH = str(get_runtime_settings().assistant_deployments_path)


def _now_iso() -> str:
    return datetime.now().isoformat()


def _proactive_key(deployment_id: str, task_id: str) -> str:
    return f"{deployment_id}:{task_id}"


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
        self._proactive_history: List[Dict[str, Any]] = []
        self._pending_proactive_approvals: Dict[str, Dict[str, Any]] = {}
        self._pending_tool_approvals: Dict[str, Dict[str, Any]] = {}
        self._approval_history: List[Dict[str, Any]] = []
        self._tool_approval_history: List[Dict[str, Any]] = []
        self._proactive_runtime: Dict[str, Dict[str, Any]] = {}
        self._proactive_loops: Dict[str, asyncio.Task] = {}

    def initialize(self, channel_registry=None, channel_pool=None):
        self._channel_registry = channel_registry
        self._channel_pool = channel_pool
        self._load()
        log_print(f"Assistant deployments initialized ({len(self._deployments)} deployments)")

    def set_channel_pool(self, channel_pool) -> None:
        self._channel_pool = channel_pool

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

    def resolve_for_message(self, channel_id: str, content: str) -> tuple[Optional[AssistantDeploymentConfig], Optional[AssistantDeploymentConfig], Optional[dict]]:
        primary = self.find_for_channel(channel_id)
        if primary is None:
            return None, None, None
        handoff = self._match_routing_rule(primary, content)
        if handoff is None:
            return primary, primary, None
        target = self._deployments.get(handoff["target_deployment_id"])
        if target is None or not target.enabled:
            return primary, primary, None
        handoff["target_name"] = target.name
        handoff["source_name"] = primary.name
        return primary, target, handoff

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
        self._runtime_stats.pop(deployment_id, None)
        self._handoff_history = [
            row for row in self._handoff_history
            if row.get("source_deployment_id") != deployment_id and row.get("target_deployment_id") != deployment_id
        ]
        self._message_history = [
            row for row in self._message_history
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
            if not rule.target_deployment_id or not rule.keywords:
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
            task.interval_sec = max(30, int(task.interval_sec or 0))
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

    def _match_routing_rule(self, deployment: AssistantDeploymentConfig, content: str) -> Optional[dict]:
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
                    "reason": f"matched keyword(s): {', '.join(matched)}",
                }
        return None

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
        elif key in self._proactive_loops and row.get("status") != "running":
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
                }
            )
            self._message_history = self._message_history[-200:]

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
        existing = self._proactive_loops.get(key)
        if existing and not existing.done():
            return
        runtime = self._proactive_runtime.setdefault(key, self._empty_proactive_runtime(task))
        runtime["status"] = "scheduled"
        runtime["next_run_at"] = (datetime.now() + timedelta(seconds=max(30, task.interval_sec))).isoformat()
        self._proactive_loops[key] = asyncio.create_task(self._proactive_loop(deployment.id, task.id))

    async def _stop_proactive_tasks(
        self, deployment_id: str, *, keep_task_ids: Optional[set[str]] = None
    ) -> None:
        prefix = f"{deployment_id}:"
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
        for key, task in list(self._proactive_loops.items()):
            self._proactive_loops.pop(key, None)
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            runtime = self._proactive_runtime.get(key)
            if runtime is not None:
                runtime["status"] = "stopped"
                runtime["next_run_at"] = None

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
        delivered = False
        pending_approval = False
        approval_id = None
        delivery_channel_id = None
        delivery_recipient_id = None

        try:
            if self._channel_pool is None:
                raise RuntimeError("Assistant deployment pool is not available")
            result = await self._channel_pool.chat(
                message=task.prompt,
                session_id=f"deploytask_{deployment.id}_{task.id}",
                toolkits=list(deployment.toolkit_names) if deployment.toolkit_names else None,
                sender_name=deployment.name,
                user_id=deployment.created_by or f"deployment:{deployment.id}",
                extra_instructions=extra_instructions,
                model_source=deployment.model_source,
                model_name=deployment.model_name,
                skill_names=list(deployment.skill_names),
                assistant_name=deployment.name,
                assistant_description=deployment.description or None,
            )
            if result.get("error"):
                raise RuntimeError(str(result.get("error")))
            preview = str(result.get("response", "") or "")
            if task.send_response:
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
        except Exception as exc:
            error = str(exc)
            preview = error

        runtime["run_count"] = int(runtime.get("run_count") or 0) + 1
        runtime["last_run_at"] = now
        runtime["last_status"] = "error" if error else ("pending_approval" if pending_approval else "ok")
        runtime["last_preview"] = preview[:240]
        runtime["last_error"] = error[:240] if error else None
        runtime["last_delivery_channel_id"] = delivery_channel_id
        runtime["last_delivery_recipient_id"] = delivery_recipient_id
        runtime["last_delivered_at"] = now if delivered else None
        runtime["last_approval_id"] = approval_id
        runtime["status"] = "scheduled" if key in self._proactive_loops else "stopped"
        if key in self._proactive_loops:
            runtime["next_run_at"] = (datetime.now() + timedelta(seconds=max(30, task.interval_sec))).isoformat()

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
            "reason": reason,
            "status": "error" if error else ("pending_approval" if pending_approval else "ok"),
            "preview": preview[:240],
            "error": error[:240] if error else None,
            "delivered": delivered,
            "approval_id": approval_id,
            "channel_id": delivery_channel_id,
            "recipient_id": delivery_recipient_id,
        }
        self._proactive_history.append(event)
        self._proactive_history = self._proactive_history[-100:]
        return event

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
        if str(status).lower() != "running":
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
        if str(status).lower() != "running":
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
        for rule in routing_rules:
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
            if task.interval_sec < 30:
                raise HTTPException(400, f"Proactive task '{task.name}' must use an interval of at least 30 seconds")
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

    @app.post("/assistant-deployments/list")
    async def assistant_deployment_list(request: Request):
        user = _require_auth(request)
        _, is_admin = _get_user(request)
        return {"deployments": deployment_mgr.list(user_id=user.id, is_admin=is_admin)}

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
