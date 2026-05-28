"""Task API routes — GET /api/tasks for listing and querying subagent tasks."""

from fastapi.responses import JSONResponse


def get_task_list_handler(core):
    async def task_list(
        status: str = "",
        runtime: str = "",
        owner_key: str = "",
        limit: int = 50,
        offset: int = 0,
    ):
        try:
            from core.task_registry import list_tasks, get_summary
            if status or runtime or owner_key:
                tasks = list_tasks(
                    status=status or None,
                    runtime=runtime or None,
                    owner_key=owner_key or None,
                    limit=min(limit, 200),
                    offset=offset,
                )
                return JSONResponse(content={
                    "tasks": [
                        {
                            "task_id": t.task_id,
                            "status": t.status.value,
                            "runtime": t.runtime.value,
                            "task_kind": t.task_kind,
                            "created_at": t.created_at,
                            "completed_at": t.completed_at,
                            "result_summary": t.result_summary,
                        }
                        for t in tasks
                    ],
                    "count": len(tasks),
                })
            return JSONResponse(content={
                "summary": {
                    "total": get_summary().total,
                    "active": get_summary().active,
                    "failures": get_summary().failures,
                }
            })
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})
    return task_list
