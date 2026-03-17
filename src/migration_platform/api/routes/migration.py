"""
Migration API routes — updated for LangGraph 1.x interrupt() pattern.

LangGraph 1.x change:
  - Approval resumes via update_state() passing the interrupt response,
    then graph.invoke(None, config) to continue from the interrupted node.
"""
from __future__ import annotations

import asyncio
import io
import json
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from langgraph.types import Command

from migration_platform.core.exceptions import MigrationNotFoundError
from migration_platform.core.logging import get_logger
from migration_platform.domain.schemas.approval import ApprovalDecision, ApprovalResponse
from migration_platform.domain.schemas.migration import (
    ArtifactsResponse, MigrationStatusResponse, StartMigrationRequest,
)
from migration_platform.workflows.state import MigrationState

router = APIRouter(prefix="/api/migrations", tags=["migrations"])
logger = get_logger(__name__)

_graph = None
_state_store = None


def init_router(graph, state_store) -> None:
    global _graph, _state_store
    _graph = graph
    _state_store = state_store


@router.post("", response_model=MigrationStatusResponse, status_code=202)
async def start_migration(
    req: StartMigrationRequest,
    background_tasks: BackgroundTasks,
) -> MigrationStatusResponse:
    migration_id = str(uuid.uuid4())
    initial_state: MigrationState = {
        "migration_id":           migration_id,
        "repo_url":               req.repo_url,
        "repo_local_path":        "",
        "file_manifest":          {},
        "entry_points":           [],
        "chunk_count":            0,
        "soap_report":            {},
        "jdbc_map":               {},
        "module_clusters":        [],
        "module_count":           0,
        "arch_plan":              {},
        "diagrams":               [],
        "migration_plan":         {},
        "sequence_diagrams":      [],
        "soap_integration_count": 0,
        "approval_status":        "pending",
        "approval_comment":       "",
        "validation_report":      {},
        "generated_files":        [],
        "build_result":           {},
        "artifact_paths":         {},
        "current_phase":          "started",
        "errors":                 [],
        "retry_count":            0,
        "messages":               [],
    }

    if _state_store:
        _state_store.create_migration(migration_id, req.repo_url)

    if _graph:
        background_tasks.add_task(_run_graph, migration_id, initial_state)

    logger.info("migration.started", migration_id=migration_id, repo_url=req.repo_url)
    return MigrationStatusResponse(
        migration_id=migration_id,
        status="started",
        approval_status="pending",
        repo_url=req.repo_url,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@router.get("/{migration_id}", response_model=MigrationStatusResponse)
async def get_status(migration_id: str) -> MigrationStatusResponse:
    if not _state_store:
        raise HTTPException(status_code=503, detail="State store not initialised")
    record = _state_store.get_migration(migration_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Migration {migration_id} not found")
    progress          = _state_store.get_progress(migration_id)
    file_counts       = _state_store.get_file_type_counts(migration_id)
    total_file_counts = _state_store.get_total_file_type_counts(migration_id)
    return MigrationStatusResponse(
        migration_id=migration_id,
        status=record.get("status", "unknown"),
        approval_status=record.get("approval_status", "pending"),
        repo_url=record.get("repo_url", ""),
        created_at=record.get("created_at") or datetime.utcnow(),
        updated_at=record.get("updated_at") or datetime.utcnow(),
        file_counts=file_counts,
        total_file_counts=total_file_counts,
        chunk_count=progress.get("total_chunks", 0),
        progress_pct=_calc_progress(record.get("status", "")),
    )


@router.get("/{migration_id}/artifacts", response_model=ArtifactsResponse)
async def get_artifacts(migration_id: str) -> ArtifactsResponse:
    if not (_graph and _state_store):
        raise HTTPException(status_code=503, detail="Platform not initialised")
    record = _state_store.get_migration(migration_id)
    if not record:
        raise HTTPException(status_code=404, detail="Migration not found")
    try:
        gs = _graph.get_state(config={"configurable": {"thread_id": migration_id}})
        values = gs.values if gs else {}
    except Exception:
        values = {}

    # Build download_urls if output files exist on disk
    from migration_platform.config.settings import get_settings
    settings = get_settings()
    output_base = Path(settings.output_dir) / migration_id
    download_urls: dict[str, str] = {}
    if (output_base / "spring-boot").exists():
        download_urls["spring-boot"] = f"/api/migrations/{migration_id}/download/spring-boot"
    if (output_base / "react").exists():
        download_urls["react"] = f"/api/migrations/{migration_id}/download/react"
    if output_base.exists():
        download_urls["all"] = f"/api/migrations/{migration_id}/download/all"

    return ArtifactsResponse(
        migration_id=migration_id,
        approval_status=record.get("approval_status", "pending"),
        diagrams=values.get("diagrams", []),
        soap_report=values.get("soap_report", {}),
        migration_plan=values.get("migration_plan", {}),
        sequence_diagrams=values.get("sequence_diagrams", []),
        arch_plan=values.get("arch_plan", {}),
        download_urls=download_urls,
    )


@router.get("/{migration_id}/download/{project}")
async def download_project(migration_id: str, project: str) -> StreamingResponse:
    """
    Download generated code as a ZIP archive.

    project = "spring-boot" | "react" | "all"
    Returns a streaming ZIP so large projects don't need to be buffered fully.
    """
    from migration_platform.config.settings import get_settings
    settings = get_settings()
    output_base = Path(settings.output_dir) / migration_id

    if project == "all":
        source_dir = output_base
    elif project in ("spring-boot", "react"):
        source_dir = output_base / project
    else:
        raise HTTPException(status_code=400, detail=f"Unknown project type: {project}")

    if not source_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Generated output not found at {source_dir}. "
                   "Code generation may not have completed yet."
        )

    # Build ZIP in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(source_dir.rglob("*")):
            if file_path.is_file():
                zf.write(file_path, arcname=file_path.relative_to(source_dir))
    buf.seek(0)

    filename = f"{migration_id[:8]}-{project}.zip"
    logger.info("download.serving", migration_id=migration_id, project=project, zip=filename)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{migration_id}/approve", response_model=ApprovalResponse)
async def approve_migration(
    migration_id: str,
    decision: ApprovalDecision,
    background_tasks: BackgroundTasks,
) -> ApprovalResponse:
    """
    LangGraph 1.x interrupt() resume pattern:

    1. update_state() injects the human decision as the interrupt() return value
    2. graph.invoke(None, config) resumes the graph from where interrupt() paused
    """
    if not (_graph and _state_store):
        raise HTTPException(status_code=503, detail="Platform not initialised")

    record = _state_store.get_migration(migration_id)
    if not record:
        raise HTTPException(status_code=404, detail="Migration not found")

    config = {"configurable": {"thread_id": migration_id}}

    # Persist decision in DuckDB
    _state_store.set_approval(migration_id, decision.status, decision.comment)

    # LangGraph 1.x: resume the interrupted graph by passing Command(resume=value).
    # This feeds the decision directly back as the return value of interrupt(),
    # so _await_approval_node receives {"status": ..., "comment": ...} correctly.
    # update_state() alone does NOT resume interrupt() — it only injects state.
    resume_value = {"status": decision.status, "comment": decision.comment}
    background_tasks.add_task(_resume_graph, migration_id, resume_value)

    next_phase = "Phase B — code generation" if decision.status == "approved" \
                 else "Phase A — plan regeneration"

    logger.info("migration.approval_decision",
                migration_id=migration_id, decision=decision.status)
    return ApprovalResponse(
        migration_id=migration_id,
        status=decision.status,
        next_phase=next_phase,
        message=f"Workflow resumed — {next_phase}",
    )


@router.websocket("/{migration_id}/ws")
async def websocket_progress(websocket: WebSocket, migration_id: str) -> None:
    await websocket.accept()
    logger.info("websocket.connected", migration_id=migration_id)
    _TERMINAL_STATUSES = {"completed", "error", "failed", "validation_blocked"}
    try:
        while True:
            if _state_store:
                record = _state_store.get_migration(migration_id)
                if record:
                    status = record.get("status", "unknown")
                    payload = json.dumps({
                        "migration_id":  migration_id,
                        "phase":         record.get("current_phase", "unknown"),
                        "status":        status,
                        "progress_pct":  _calc_progress(status),
                        "approval":      record.get("approval_status", "pending"),
                    })
                    await websocket.send_text(payload)
                    # Close from server side once the workflow reaches a terminal state
                    # so the UI immediately transitions rather than waiting for a timeout.
                    if status in _TERMINAL_STATUSES:
                        logger.info("websocket.terminal_state", migration_id=migration_id, status=status)
                        break
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        logger.info("websocket.disconnected", migration_id=migration_id)
    except asyncio.CancelledError:
        # Server shutting down — close cleanly and re-raise so uvicorn can finish
        logger.info("websocket.server_shutdown", migration_id=migration_id)
        raise
    except Exception as exc:
        logger.warning("websocket.error", migration_id=migration_id, error=str(exc))
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


def _persist_chunk(migration_id: str, chunk: dict) -> None:
    """Write LangGraph state updates from a streamed chunk back to DuckDB.

    With stream_mode="updates" each chunk is {node_name: {state_key: value, ...}}.

    Special cases:
      - "__interrupt__" key: graph has suspended at interrupt() waiting for human
        approval — persist "awaiting_approval" so the WebSocket signals the UI.
      - Normal node output: extract current_phase and approval_status.
    """
    if not _state_store:
        return

    # ── Interrupt gate ─────────────────────────────────────────────────────────
    # LangGraph 1.x emits {"__interrupt__": (...,)} when interrupt() suspends.
    # _await_approval_node never returns at this point, so we must handle it here.
    if "__interrupt__" in chunk:
        _state_store.update_status(migration_id, "awaiting_approval", "awaiting_approval")
        logger.info("workflow.phase_persisted", migration_id=migration_id, phase="awaiting_approval")
        # ── State snapshot backup ───────────────────────────────────────────────
        # Save the full Phase-A state to DuckDB state_json so we can recover it
        # if the checkpointer is ever lost (e.g. server restart before persistence
        # was introduced). _resume_graph reads this back when it detects a missing
        # checkpoint.
        if _graph:
            try:
                config = {"configurable": {"thread_id": migration_id}}
                gs = _graph.get_state(config)
                if gs and gs.values:
                    _state_store.save_state_json(migration_id, dict(gs.values))
                    logger.info("workflow.state_snapshot_saved", migration_id=migration_id)
            except Exception as snap_exc:
                logger.warning("workflow.state_snapshot_failed", error=str(snap_exc))
        return

    # ── Regular node output ────────────────────────────────────────────────────
    for node_output in chunk.values():
        if not isinstance(node_output, dict):
            continue
        phase = node_output.get("current_phase")
        if phase:
            _state_store.update_status(migration_id, phase, phase)
            logger.debug("workflow.phase_persisted", migration_id=migration_id, phase=phase)
        approval = node_output.get("approval_status")
        if approval and approval != "pending":
            _state_store.set_approval(
                migration_id, approval, node_output.get("approval_comment", "")
            )


async def _run_graph(migration_id: str, initial_state: MigrationState) -> None:
    try:
        config = {"configurable": {"thread_id": migration_id}}
        async for chunk in _graph.astream(initial_state, config=config, stream_mode="updates"):
            logger.debug("workflow.step", migration_id=migration_id, chunk=str(chunk)[:120])
            _persist_chunk(migration_id, chunk)
    except Exception as exc:
        logger.error("workflow.error", migration_id=migration_id, error=str(exc))
        if _state_store:
            _state_store.set_error(migration_id, str(exc))


async def _resume_graph(migration_id: str, resume_value: dict) -> None:
    """
    Resume after interrupt() — Command(resume=value) feeds the value back to interrupt().

    Checkpoint-loss recovery
    ------------------------
    If the server was restarted while using MemorySaver (before PersistentMemorySaver
    was introduced), the checkpoint is gone.  LangGraph then starts a fresh run with
    an empty state, which raises KeyError when node functions access required state keys.

    Detection: catch KeyError / ValueError from missing state keys.
    Recovery:  read the Phase-A state snapshot previously saved to DuckDB state_json,
               inject it as the initial state for a new graph run, then fast-forward
               through Phase A by skipping re-analysis and jumping straight to approval.
    Fallback:  if no snapshot exists, mark the migration as failed with a clear message.
    """
    config = {"configurable": {"thread_id": migration_id}}

    # ── Attempt 1: normal LangGraph resume ────────────────────────────────────
    try:
        async for chunk in _graph.astream(
            Command(resume=resume_value), config=config, stream_mode="updates"
        ):
            logger.debug("workflow.resume_step", migration_id=migration_id, chunk=str(chunk)[:120])
            _persist_chunk(migration_id, chunk)
        # Graph reached END — mark the migration completed so the UI transitions to 100%
        if _state_store:
            _state_store.update_status(migration_id, "completed", "completed")
            logger.info("workflow.completed", migration_id=migration_id)
        return  # success — exit early
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning(
            "workflow.checkpoint_missing",
            migration_id=migration_id,
            error=str(exc),
            hint="Checkpoint was likely lost due to a server restart. Attempting DuckDB recovery.",
        )
    except Exception as exc:
        logger.error("workflow.resume_error", migration_id=migration_id, error=str(exc))
        if _state_store:
            _state_store.set_error(migration_id, str(exc))
        return

    # ── Attempt 2: DuckDB snapshot recovery ───────────────────────────────────
    if not (_graph and _state_store):
        return

    record = _state_store.get_migration(migration_id)
    import json as _json
    raw_json = record.get("state_json") if record else None
    saved_state: dict = {}
    if raw_json:
        try:
            saved_state = _json.loads(raw_json) if isinstance(raw_json, str) else raw_json
        except Exception:
            saved_state = {}

    if not saved_state or not saved_state.get("migration_id"):
        # No usable snapshot → tell the user to start a new migration
        msg = (
            "Workflow checkpoint was lost (the server restarted while using in-memory "
            "checkpointing). The Phase A analysis results are no longer available. "
            "Please start a new migration to regenerate the plan."
        )
        _state_store.set_error(migration_id, msg)
        logger.error("workflow.checkpoint_unrecoverable", migration_id=migration_id)
        return

    # Restore the Phase-A state, mark approval, then start a fresh graph run.
    # The graph will re-run all Phase-A agents but ChromaDB embeddings already
    # exist so parse_and_embed will be near-instant.
    logger.info(
        "workflow.checkpoint_recovery_from_snapshot",
        migration_id=migration_id,
        snapshot_keys=list(saved_state.keys()),
    )
    restored: dict = {**saved_state}
    restored["approval_status"]  = resume_value.get("status", "approved")
    restored["approval_comment"] = resume_value.get("comment", "")
    restored["current_phase"]    = "approval_received"

    try:
        _state_store.update_status(migration_id, "approval_received", "approval_received")
        async for chunk in _graph.astream(restored, config=config, stream_mode="updates"):
            logger.debug("workflow.recovery_step", migration_id=migration_id, chunk=str(chunk)[:120])
            _persist_chunk(migration_id, chunk)
        # Graph reached END — mark completed so the UI transitions to 100%
        _state_store.update_status(migration_id, "completed", "completed")
        logger.info("workflow.completed_via_recovery", migration_id=migration_id)
    except Exception as exc:
        logger.error("workflow.recovery_failed", migration_id=migration_id, error=str(exc))
        _state_store.set_error(
            migration_id,
            f"Recovery run failed: {exc}. Please start a new migration."
        )


def _calc_progress(status: str) -> float:
    return {
        "started": 5.0, "ingested": 15.0, "parsed": 35.0, "graphed": 50.0,
        "detected": 60.0, "designed": 70.0, "planned": 80.0,
        "awaiting_approval": 80.0, "approval_received": 82.0,
        "validated": 85.0,
        # dispatching = graph fanning-out to parallel module workers
        "dispatching": 87.0,
        # validation_blocked = critical issues found; graph routed to END
        "validation_blocked": 85.0,
        "generating": 92.0, "generated": 95.0,
        "built": 98.0, "completed": 100.0,
    }.get(status, 0.0)
