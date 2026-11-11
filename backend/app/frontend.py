"""为 Vue history 路由提供入口，同时保留 API 和静态资源的正常 404。"""

import re

from fastapi.staticfiles import StaticFiles
from starlette.types import Scope


class FrontendFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope):
        route_path = path.replace("\\", "/")
        if scope["method"] in {"GET", "HEAD"} and re.fullmatch(r"(?:login|screen|videos/[^/.]+)/*", route_path):
            path = "index.html"
        return await super().get_response(path, scope)
