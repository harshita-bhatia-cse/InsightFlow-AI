from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database.connection import SessionLocal
from app.database.models import User, Workspace
from app.workspaces.schemas import WorkspaceCreate, WorkspaceResponse
from app.workspaces.service import WorkspaceService
from app.audit.service import record_event


router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = WorkspaceService(db)

    workspace = service.create_workspace(
        name=payload.name,
        description=payload.description,
        owner_id=current_user.id,
    )
    record_event(
        db,
        actor_user_id=current_user.id,
        action="workspace.create",
        resource_type="workspace",
        resource_id=str(workspace.id),
        outcome="success",
        request_id=request.state.request_id,
    )
    db.commit()

    return {
        "id": workspace.id,
        "name": workspace.name,
        "description": workspace.description,
        "owner_id": workspace.owner_id,
        "created_at": workspace.created_at,
    }


@router.get("", response_model=list[WorkspaceResponse])
def list_workspaces(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = WorkspaceService(db)
    workspaces = service.list_workspaces_for_user(current_user.id)

    return [
        {
            "id": workspace.id,
            "name": workspace.name,
            "description": workspace.description,
            "owner_id": workspace.owner_id,
            "created_at": workspace.created_at,
        }
        for workspace in workspaces
    ]


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
def get_workspace(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = WorkspaceService(db)
    workspace = service.get_workspace_by_id(workspace_id)

    if workspace is None or workspace.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    return {
        "id": workspace.id,
        "name": workspace.name,
        "description": workspace.description,
        "owner_id": workspace.owner_id,
        "created_at": workspace.created_at,
    }


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace(
    workspace_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = WorkspaceService(db)
    deleted = service.delete_workspace(workspace_id, current_user.id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )
    record_event(
        db,
        actor_user_id=current_user.id,
        action="workspace.delete",
        resource_type="workspace",
        resource_id=str(workspace_id),
        outcome="success",
        request_id=request.state.request_id,
    )
    db.commit()