from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database.connection import SessionLocal
from app.database.models import User
from app.permissions.schemas import (
    ProjectMemberCreate,
    ProjectMemberResponse,
    ProjectMemberRoleUpdate,
)
from app.permissions.services import ProjectPermissionService
from app.audit.service import record_event


router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_project_owner(
    project_id: int,
    current_user: User,
    db: Session,
) -> ProjectPermissionService:
    service = ProjectPermissionService(db)

    if not service.user_owns_project(
        project_id=project_id,
        user_id=current_user.id,
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Project not found or not owned "
                "by the current user."
            ),
        )

    return service


@router.post(
    "/projects/{project_id}/members",
    response_model=ProjectMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_project_member(
    project_id: int,
    payload: ProjectMemberCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = require_project_owner(
        project_id=project_id,
        current_user=current_user,
        db=db,
    )

    if not service.user_exists(payload.user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    if service.get_member(
        project_id=project_id,
        user_id=payload.user_id,
    ) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this project.",
        )

    member = service.add_member(
        project_id=project_id,
        user_id=payload.user_id,
        role=payload.role,
    )

    if member is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project member could not be created.",
        )

    record_event(
        db,
        actor_user_id=current_user.id,
        action="project.member_add",
        resource_type="project_member",
        resource_id=str(member.id),
        outcome="success",
        request_id=request.state.request_id,
        metadata={"project_id": project_id, "user_id": payload.user_id, "role": payload.role},
    )
    db.commit()

    return member


@router.get(
    "/projects/{project_id}/members",
    response_model=list[ProjectMemberResponse],
)
def list_project_members(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = require_project_owner(
        project_id=project_id,
        current_user=current_user,
        db=db,
    )

    return service.list_members(project_id=project_id)


@router.patch(
    "/projects/{project_id}/members/{user_id}",
    response_model=ProjectMemberResponse,
)
def update_project_member_role(
    project_id: int,
    user_id: int,
    payload: ProjectMemberRoleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = require_project_owner(
        project_id=project_id,
        current_user=current_user,
        db=db,
    )

    member = service.update_member_role(
        project_id=project_id,
        user_id=user_id,
        role=payload.role,
    )

    if member is None:
        if (
            service.get_member(project_id=project_id, user_id=user_id)
            is not None
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The final project owner cannot be demoted.",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project member not found.",
        )

    record_event(
        db,
        actor_user_id=current_user.id,
        action="project.member_role_change",
        resource_type="project_member",
        resource_id=str(member.id),
        outcome="success",
        request_id=request.state.request_id,
        metadata={"project_id": project_id, "user_id": user_id, "role": payload.role},
    )
    db.commit()

    return member


@router.delete(
    "/projects/{project_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_project_member(
    project_id: int,
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = require_project_owner(
        project_id=project_id,
        current_user=current_user,
        db=db,
    )

    removed = service.remove_member(
        project_id=project_id,
        user_id=user_id,
    )

    if not removed:
        member = service.get_member(
            project_id=project_id,
            user_id=user_id,
        )
        if member is not None and member.role == "owner":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The final project owner cannot be removed.",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project member not found.",
        )

    record_event(
        db,
        actor_user_id=current_user.id,
        action="project.member_remove",
        resource_type="project_member",
        resource_id=f"{project_id}:{user_id}",
        outcome="success",
        request_id=request.state.request_id,
        metadata={"project_id": project_id, "user_id": user_id},
    )
    db.commit()

    return None