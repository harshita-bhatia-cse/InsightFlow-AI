from sqlalchemy.orm import Session

from app.database.models import Project, ProjectMember, Workspace


class ProjectService:
    def __init__(self, db: Session):
        self.db = db

    def create_project(
        self,
        name: str,
        description: str | None,
        workspace_id: int,
        owner_id: int,
    ) -> Project | None:
        workspace = (
            self.db.query(Workspace)
            .filter(
                Workspace.id == workspace_id,
                Workspace.owner_id == owner_id,
            )
            .first()
        )

        if workspace is None:
            return None

        project = Project(
            name=name.strip(),
            description=description.strip() if description else None,
            workspace_id=workspace_id,
        )

        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)

        return project

    def get_project_for_owner(
        self,
        project_id: int,
        owner_id: int,
    ) -> Project | None:
        return (
            self.db.query(Project)
            .join(Workspace, Project.workspace_id == Workspace.id)
            .filter(
                Project.id == project_id,
                Workspace.owner_id == owner_id,
            )
            .first()
        )

    def get_project_for_user(
        self,
        project_id: int,
        user_id: int,
    ) -> Project | None:
        owner_project = self.get_project_for_owner(
            project_id=project_id,
            owner_id=user_id,
        )
        if owner_project is not None:
            return owner_project

        return (
            self.db.query(Project)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .filter(
                Project.id == project_id,
                ProjectMember.user_id == user_id,
            )
            .first()
        )

    def list_projects_for_owner(
        self,
        owner_id: int,
    ) -> list[Project]:
        return (
            self.db.query(Project)
            .join(Workspace, Project.workspace_id == Workspace.id)
            .filter(Workspace.owner_id == owner_id)
            .order_by(Project.created_at.desc())
            .all()
        )

    def list_projects_for_user(
        self,
        user_id: int,
    ) -> list[Project]:
        owned = self.list_projects_for_owner(owner_id=user_id)
        member_projects = (
            self.db.query(Project)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .filter(ProjectMember.user_id == user_id)
            .order_by(Project.created_at.desc())
            .all()
        )
        projects_by_id = {project.id: project for project in owned}
        for project in member_projects:
            projects_by_id.setdefault(project.id, project)
        return sorted(
            projects_by_id.values(),
            key=lambda project: project.created_at,
            reverse=True,
        )

    def delete_project(
        self,
        project_id: int,
        owner_id: int,
    ) -> bool:
        project = self.get_project_for_owner(
            project_id=project_id,
            owner_id=owner_id,
        )

        if project is None:
            return False

        self.db.delete(project)
        self.db.commit()

        return True