from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


def format_memories_for_prompt(memories: list[dict[str, Any]]) -> str:
    if not memories:
        return "No approved memories were retrieved."
    lines = ["Approved memory context:"]
    for index, memory in enumerate(memories, start=1):
        memory_type = memory.get("memory_type", "context")
        score = memory.get("score")
        score_text = f", score={score}" if score is not None else ""
        lines.append(f"{index}. [{memory_type}{score_text}] {memory['content']}")
    return "\n".join(lines)


@dataclass
class MemoryGatewayClient:
    base_url: str = "http://localhost:8000"
    api_key: str = "backend-demo-key"
    timeout: float = 15.0

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self.api_key}

    def search(
        self,
        query: str,
        project_id: str | None,
        memory_types: list[str] | None = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        payload = {
            "query": query,
            "project_id": project_id,
            "memory_types": memory_types,
            "top_k": top_k,
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/memories/search",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def list_zones(self) -> list[dict[str, Any]]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(f"{self.base_url}/v1/zones", headers=self._headers())
            response.raise_for_status()
            return response.json()

    def list_projects(self) -> list[dict[str, Any]]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(f"{self.base_url}/v1/projects", headers=self._headers())
            response.raise_for_status()
            return response.json()

    def create_project(self, project_id: str, name: str, description: str = "") -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/projects",
                headers=self._headers(),
                json={"id": project_id, "name": name, "description": description},
            )
            response.raise_for_status()
            return response.json()

    def ingest(
        self,
        content: str,
        project_id: str | None = None,
        source: str = "api",
        content_kind: str = "text",
        source_url: str | None = None,
        source_title: str | None = None,
        model_profile_id: str | None = None,
        auto_approve_public_low: bool = True,
    ) -> dict[str, Any]:
        payload = {
            "content": content,
            "content_kind": content_kind,
            "source": source,
            "project_id": project_id,
            "source_url": source_url,
            "source_title": source_title,
            "model_profile_id": model_profile_id,
            "auto_approve_public_low": auto_approve_public_low,
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/ingest",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def list_inbox(self, status: str = "pending_review") -> list[dict[str, Any]]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.base_url}/v1/inbox",
                headers=self._headers(),
                params={"status": status},
            )
            response.raise_for_status()
            return response.json()

    def approve_inbox_item(
        self,
        inbox_id: str,
        memory_zone: str | None = None,
        memory_type: str | None = None,
        project_id: str | None = None,
        tags: list[str] | None = None,
        note: str = "",
    ) -> dict[str, Any]:
        payload = {
            "memory_zone": memory_zone,
            "memory_type": memory_type,
            "project_id": project_id,
            "tags": tags,
            "note": note,
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/inbox/{inbox_id}/approve",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def reject_inbox_item(self, inbox_id: str, reason: str = "") -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/inbox/{inbox_id}/reject",
                headers=self._headers(),
                json={"reason": reason},
            )
            response.raise_for_status()
            return response.json()

    def compose_context(
        self,
        task: str,
        project_id: str | None = None,
        zones: list[str] | None = None,
        grant_token: str | None = None,
        memory_types: list[str] | None = None,
        max_tokens: int = 1200,
        include_graph: bool = True,
        top_k: int = 8,
        retrieval_mode: str = "summary_first",
        use_llm_rerank: bool = True,
    ) -> dict[str, Any]:
        payload = {
            "task": task,
            "project_id": project_id,
            "zones": zones or ["public_profile"],
            "grant_token": grant_token,
            "memory_types": memory_types,
            "max_tokens": max_tokens,
            "include_graph": include_graph,
            "top_k": top_k,
            "retrieval_mode": retrieval_mode,
            "use_llm_rerank": use_llm_rerank,
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/context/compose",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def analyze_capture(
        self,
        content: str,
        content_kind: str = "text",
        project_id: str | None = None,
        source_url: str | None = None,
        source_title: str | None = None,
        asset_path: str | None = None,
        model_profile_id: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "content": content,
            "content_kind": content_kind,
            "capture_source": "clipboard",
            "project_id": project_id,
            "source_url": source_url,
            "source_title": source_title,
            "asset_path": asset_path,
            "model_profile_id": model_profile_id,
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/captures/analyze",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def commit_capture(
        self,
        content: str,
        memory_zone: str,
        memory_type: str,
        project_id: str | None = None,
        content_kind: str = "text",
        tags: list[str] | None = None,
        source_url: str | None = None,
        source_title: str | None = None,
        asset_path: str | None = None,
        approve_now: bool = True,
    ) -> dict[str, Any]:
        payload = {
            "content": content,
            "content_kind": content_kind,
            "capture_source": "clipboard",
            "memory_zone": memory_zone,
            "memory_type": memory_type,
            "project_id": project_id,
            "tags": tags or [],
            "source_url": source_url,
            "source_title": source_title,
            "asset_path": asset_path,
            "approve_now": approve_now,
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/captures/commit",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def request_grant(
        self,
        task_id: str,
        purpose: str,
        allowed_zones: list[str],
        project_id: str | None = None,
        ttl_minutes: int | None = None,
    ) -> dict[str, Any]:
        payload = {
            "task_id": task_id,
            "purpose": purpose,
            "allowed_zones": allowed_zones,
            "project_id": project_id,
            "ttl_minutes": ttl_minutes,
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/grants/request",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def request_context(
        self,
        task: str,
        project_id: str | None = None,
        zones: list[str] | None = None,
        grant_token: str | None = None,
        memory_types: list[str] | None = None,
        max_tokens: int = 1200,
        include_graph: bool = True,
        top_k: int = 8,
        task_id: str | None = None,
        purpose: str | None = None,
        ttl_minutes: int | None = None,
        retrieval_mode: str = "summary_first",
        use_llm_rerank: bool = True,
    ) -> dict[str, Any]:
        payload = {
            "task": task,
            "task_id": task_id,
            "purpose": purpose,
            "project_id": project_id,
            "zones": zones or ["public_profile"],
            "grant_token": grant_token,
            "memory_types": memory_types,
            "max_tokens": max_tokens,
            "include_graph": include_graph,
            "top_k": top_k,
            "ttl_minutes": ttl_minutes,
            "retrieval_mode": retrieval_mode,
            "use_llm_rerank": use_llm_rerank,
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/context/request",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def get_context_request(self, grant_id: str) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.base_url}/v1/context/requests/{grant_id}",
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()

    def compose_approved_context(self, grant_id: str) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/context/requests/{grant_id}/compose",
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()

    def preview_share_pack(
        self,
        project_id: str,
        name: str = "Project onboarding share",
        description: str = "",
        recipient_label: str = "",
        task: str = "Onboard me to this project.",
        allowed_zones: list[str] | None = None,
        allowed_memory_types: list[str] | None = None,
        allowed_tags: list[str] | None = None,
        excluded_memory_ids: list[str] | None = None,
        max_tokens: int = 1600,
        top_k: int = 12,
    ) -> dict[str, Any]:
        payload = {
            "project_id": project_id,
            "name": name,
            "description": description,
            "recipient_label": recipient_label,
            "task": task,
            "allowed_zones": allowed_zones or ["work_context"],
            "allowed_memory_types": allowed_memory_types
            or ["context", "relationship", "preference", "procedure", "lesson", "anti_pattern"],
            "allowed_tags": allowed_tags or [],
            "excluded_memory_ids": excluded_memory_ids or [],
            "max_tokens": max_tokens,
            "top_k": top_k,
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/share-packs/preview",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def create_share_pack(
        self,
        project_id: str,
        name: str = "Project onboarding share",
        description: str = "",
        recipient_label: str = "",
        task: str = "Onboard me to this project.",
        allowed_zones: list[str] | None = None,
        allowed_memory_types: list[str] | None = None,
        allowed_tags: list[str] | None = None,
        excluded_memory_ids: list[str] | None = None,
        max_tokens: int = 1600,
        top_k: int = 12,
        ttl_days: int = 7,
        max_uses: int = 20,
    ) -> dict[str, Any]:
        payload = {
            "project_id": project_id,
            "name": name,
            "description": description,
            "recipient_label": recipient_label,
            "task": task,
            "allowed_zones": allowed_zones or ["work_context"],
            "allowed_memory_types": allowed_memory_types
            or ["context", "relationship", "preference", "procedure", "lesson", "anti_pattern"],
            "allowed_tags": allowed_tags or [],
            "excluded_memory_ids": excluded_memory_ids or [],
            "max_tokens": max_tokens,
            "top_k": top_k,
            "ttl_days": ttl_days,
            "max_uses": max_uses,
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/share-packs",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def list_share_packs(self, status: str | None = None) -> list[dict[str, Any]]:
        params = {"status": status} if status else None
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.base_url}/v1/share-packs",
                headers=self._headers(),
                params=params,
            )
            response.raise_for_status()
            return response.json()

    def compose_share_pack(
        self,
        share_pack_id: str,
        share_token: str,
        task: str = "Onboard me to this project.",
        max_tokens: int = 1600,
        top_k: int = 12,
    ) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/share-packs/{share_pack_id}/compose",
                headers=self._headers(),
                json={
                    "share_token": share_token,
                    "task": task,
                    "max_tokens": max_tokens,
                    "top_k": top_k,
                },
            )
            response.raise_for_status()
            return response.json()

    def revoke_share_pack(self, share_pack_id: str) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/share-packs/{share_pack_id}/revoke",
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()

    def list_memories(
        self,
        project_id: str | None = None,
        zone: str | None = None,
        memory_type: str | None = None,
        status: str | None = None,
        query: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        params = {
            "project_id": project_id,
            "zone": zone,
            "memory_type": memory_type,
            "status": status,
            "query": query,
            "limit": limit,
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.base_url}/v1/memories",
                headers=self._headers(),
                params={key: value for key, value in params.items() if value is not None},
            )
            response.raise_for_status()
            return response.json()

    def get_memory(self, memory_id: str) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.base_url}/v1/memories/{memory_id}",
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()

    def patch_memory(self, memory_id: str, **payload: Any) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.patch(
                f"{self.base_url}/v1/memories/{memory_id}",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def supersede_memory(self, memory_id: str, **payload: Any) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/memories/{memory_id}/supersede",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def restore_memory(self, memory_id: str, reason: str = "") -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/memories/{memory_id}/restore",
                headers=self._headers(),
                json={"reason": reason},
            )
            response.raise_for_status()
            return response.json()

    def delete_memory(self, memory_id: str) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/memories/{memory_id}/delete",
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()

    def extraction_preview(
        self,
        content: str,
        project_id: str | None = None,
        content_kind: str = "text",
        memory_zone: str | None = None,
        memory_type: str | None = None,
        model_profile_id: str | None = None,
    ) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/extraction/preview",
                headers=self._headers(),
                json={
                    "content": content,
                    "content_kind": content_kind,
                    "project_id": project_id,
                    "memory_zone": memory_zone,
                    "memory_type": memory_type,
                    "model_profile_id": model_profile_id,
                },
            )
            response.raise_for_status()
            return response.json()

    def semantic_summarize(
        self,
        content: str,
        project_id: str | None = None,
        memory_zone: str = "public_profile",
        model_profile_id: str | None = None,
    ) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/semantic/summarize",
                headers=self._headers(),
                json={
                    "content": content,
                    "project_id": project_id,
                    "memory_zone": memory_zone,
                    "model_profile_id": model_profile_id,
                },
            )
            response.raise_for_status()
            return response.json()

    def semantic_judge(
        self,
        content: str,
        project_id: str | None = None,
        memory_zone: str = "public_profile",
        model_profile_id: str | None = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/semantic/judge",
                headers=self._headers(),
                json={
                    "content": content,
                    "project_id": project_id,
                    "memory_zone": memory_zone,
                    "model_profile_id": model_profile_id,
                    "top_k": top_k,
                },
            )
            response.raise_for_status()
            return response.json()

    def rebuild_summaries(self, model_profile_id: str | None = None) -> dict[str, Any]:
        params = {"model_profile_id": model_profile_id} if model_profile_id else None
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/summaries/rebuild",
                headers=self._headers(),
                params=params,
            )
            response.raise_for_status()
            return response.json()

    def list_decision_examples(
        self,
        project_id: str | None = None,
        zone: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        params = {"limit": limit}
        if project_id:
            params["project_id"] = project_id
        if zone:
            params["zone"] = zone
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.base_url}/v1/decision-examples",
                headers=self._headers(),
                params=params,
            )
            response.raise_for_status()
            return response.json()

    def approve_grant(self, grant_id: str, ttl_minutes: int | None = None) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/grants/{grant_id}/approve",
                headers=self._headers(),
                json={"ttl_minutes": ttl_minutes},
            )
            response.raise_for_status()
            return response.json()

    def get_grant(self, grant_id: str) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.base_url}/v1/grants/{grant_id}",
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()

    def search_with_grant(
        self,
        query: str,
        project_id: str | None,
        zones: list[str],
        grant_token: str | None = None,
        memory_types: list[str] | None = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        payload = {
            "query": query,
            "project_id": project_id,
            "zones": zones,
            "grant_token": grant_token,
            "memory_types": memory_types,
            "top_k": top_k,
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/vault/search",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def graph_health(self) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(f"{self.base_url}/v1/graph/health", headers=self._headers())
            response.raise_for_status()
            return response.json()

    def graph_search(
        self,
        query: str,
        project_id: str | None,
        zones: list[str],
        grant_token: str | None = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        payload = {
            "query": query,
            "project_id": project_id,
            "zones": zones,
            "grant_token": grant_token,
            "top_k": top_k,
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/graph/search",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def graph_rebuild(self) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/graph/rebuild",
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()

    def propose_memory(
        self,
        content: str,
        project_id: str | None,
        memory_type: str = "context",
        visibility: str = "project",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "content": content,
            "project_id": project_id,
            "memory_type": memory_type,
            "visibility": visibility,
            "tags": tags or [],
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/memories/proposals",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def submit_feedback(
        self,
        task_id: str,
        rating: int,
        correction: str,
        error_type: str,
        project_id: str | None = None,
        expected_behavior: str = "",
    ) -> dict[str, Any]:
        payload = {
            "task_id": task_id,
            "rating": rating,
            "correction": correction,
            "expected_behavior": expected_behavior,
            "error_type": error_type,
            "project_id": project_id,
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/feedback",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def extract_lessons(self, feedback_id: str) -> list[dict[str, Any]]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/learning/extract",
                headers=self._headers(),
                json={"feedback_id": feedback_id},
            )
            response.raise_for_status()
            return response.json()

    def approve_lesson(self, proposal_id: str) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/learning/proposals/{proposal_id}/approve",
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()

    def explain(self, memory_id: str, project_id: str | None = None) -> dict[str, Any]:
        params = {"project_id": project_id} if project_id else None
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.base_url}/v1/memories/{memory_id}/explain",
                headers=self._headers(),
                params=params,
            )
            response.raise_for_status()
            return response.json()

    def list_model_profiles(self) -> list[dict[str, Any]]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(f"{self.base_url}/v1/model-profiles", headers=self._headers())
            response.raise_for_status()
            return response.json()

    def activate_model_profile(self, profile_id: str) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/model-profiles/{profile_id}/activate",
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()

    def classify_with_model(
        self,
        content: str,
        project_id: str | None = None,
        model_profile_id: str | None = None,
    ) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/model-processing/classify",
                headers=self._headers(),
                json={
                    "content": content,
                    "project_id": project_id,
                    "model_profile_id": model_profile_id,
                },
            )
            response.raise_for_status()
            return response.json()
