"""FastAPI backend — streams agent responses as Server-Sent Events."""

import pathlib
from contextlib import asynccontextmanager
from typing import AsyncIterator

from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).parent.parent / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from agent import create_incident_agent

_agent = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _agent
    _agent = create_incident_agent()
    yield


app = FastAPI(
    title="Incident Copilot API",
    description="Autonomous DevOps incident triage powered by Gemini + Elastic + GitLab",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class TriageRequest(BaseModel):
    message: str
    session_id: str = "default"


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "agent": "incident_copilot"}


@app.post("/triage")
async def triage(req: TriageRequest) -> StreamingResponse:
    """Run the agent on a user message and stream the response."""
    if _agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    async def event_stream() -> AsyncIterator[str]:
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai.types import Content, Part

        session_service = InMemorySessionService()
        runner = Runner(
            agent=_agent,
            app_name="incident_copilot",
            session_service=session_service,
        )
        session = await session_service.create_session(
            app_name="incident_copilot",
            user_id="user",
        )
        user_content = Content(role="user", parts=[Part(text=req.message)])

        try:
            async for event in runner.run_async(
                user_id="user",
                session_id=session.id,
                new_message=user_content,
            ):
                if event.is_final_response() and event.content:
                    for part in event.content.parts:
                        if part.text:
                            yield f"data: {part.text}\n\n"
                elif hasattr(event, "get_function_calls") and event.get_function_calls():
                    for call in event.get_function_calls():
                        yield f"data: [Tool: {call.name}]\n\n"
        except Exception as exc:
            err_str = str(exc)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                yield "data: [ERROR] Gemini API rate limit reached. Please wait 60 seconds and try again.\n\n"
            else:
                yield f"data: [ERROR] Agent error: {err_str[:200]}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/triage/sync")
async def triage_sync(req: TriageRequest) -> dict:
    """Run the agent and return the full response (non-streaming, for testing)."""
    if _agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai.types import Content, Part

    session_service = InMemorySessionService()
    runner = Runner(
        agent=_agent,
        app_name="incident_copilot",
        session_service=session_service,
    )
    session = await session_service.create_session(
        app_name="incident_copilot",
        user_id="user",
    )
    user_content = Content(role="user", parts=[Part(text=req.message)])

    tool_calls_made: list[str] = []
    final_text = ""

    try:
        async for event in runner.run_async(
            user_id="user",
            session_id=session.id,
            new_message=user_content,
        ):
            if event.is_final_response() and event.content:
                for part in event.content.parts:
                    if part.text:
                        final_text += part.text
            elif hasattr(event, "get_function_calls") and event.get_function_calls():
                for call in event.get_function_calls():
                    tool_calls_made.append(call.name)
    except Exception as exc:
        err_str = str(exc)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
            raise HTTPException(
                status_code=429,
                detail="Gemini API rate limit reached (5 req/min free tier). Please wait 60 seconds and try again.",
            )
        raise

    return {
        "response": final_text,
        "tool_calls": tool_calls_made,
        "session_id": session.id,
    }
