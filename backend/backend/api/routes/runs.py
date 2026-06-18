@router.get("/{run_id}")
async def get_run(run_id: str):
    async with get_db_session() as session:
        repo = RunRepository(session)
        run = await repo.get(run_id)

        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

        return run