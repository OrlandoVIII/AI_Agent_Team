# Project Name

AI-powered development team project.

## Stack
- **Frontend:** React
- **Backend:** FastAPI (Python)
- **Database:** PostgreSQL
- **Deployment:** Docker + AWS ECS
- **CI/CD:** GitHub Actions

## Branching Model
- `main` → Production. Only the project owner can merge here.
- `develop` → Integration branch. Requires Code Reviewer Agent approval.
- `feature/{agent-type}/{task}` → Agent feature branches.

## Agents
- Frontend Agent → `feature/frontend/*`
- Backend Agent → `feature/backend/*`
- DevOps Agent → `feature/devops/*`
- UI Designer Agent → `feature/designer/*`
# retrigger
