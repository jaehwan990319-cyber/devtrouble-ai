from fastapi import APIRouter

from app.api.v1 import admin, ai_search, auth, bookmarks, comments, documents, projects, tags, users

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(projects.router)
api_router.include_router(documents.router)
api_router.include_router(tags.router)
api_router.include_router(comments.router)
api_router.include_router(bookmarks.router)
api_router.include_router(ai_search.router)
api_router.include_router(admin.router)
