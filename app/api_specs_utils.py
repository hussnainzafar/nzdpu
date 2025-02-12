"""API specs utilities."""

from dataclasses import dataclass, field

from fastapi import FastAPI
from fastapi.params import Depends
from fastapi.routing import APIRoute
from fastapi.security import OAuth2PasswordBearer

from .db.models import AuthMode, User
from .dependencies import (
    RoleAuthorization,
    get_current_user,
    get_current_user_from_api_key,
    get_current_user_from_multiple_auth,
)
from .loggers import get_nzdpu_logger

logger = get_nzdpu_logger()


@dataclass
class RouteViewer:
    app: FastAPI
    user: User | None
    user_routes: list[APIRoute] = field(default_factory=list)

    def _add_route(self, route: APIRoute):
        """
        Adds the route to the displayed routes.

        Args:
            route (APIRoute): The API route to display.
        """
        if self.user:
            logger.debug(
                f"Adding route {route} for user with roles {[group.name for group in self.user.groups]}"
            )
        else:
            logger.debug(f"Adding route {route} for unauthenticated user")
        self.user_routes.append(route)

    def _discard_route(self, route: APIRoute) -> bool:
        """
        Immediately discard routes based on a set of rules.

        Args:
            route (APIRoute): The API route

        Returns:
            bool: True if to discard
        """
        unwanted_routes = {
            "/files",
            "/files/{file_id}",
            "/files/vaults",
            "/files/vaults/{vault_id}",
        }
        no_access_paths: dict[str, dict[str, list[str]]] = {
            "/external/by-lei": {"methods": ["PATCH"]}
        }
        hide_for_unknown = {"/token/refresh"}
        show_for_unknown_only = {"/token"}
        # skip routes in unwanted_routes by default
        if route.path in unwanted_routes:
            return True
        # there are endpoints which must be able to be called without a
        # token, but should be hidden from unknown users
        if not self.user:
            if route.path in hide_for_unknown:
                return True
            if route.path in show_for_unknown_only:
                self._add_route(route)
                return True
        if self.user and route.path in show_for_unknown_only:
            return True
        # check if route in no_access_paths, and route method in methods
        if set(no_access_paths.get(route.path, {}).get("methods", [])) & set(
            route.methods
        ) == set(route.methods):  # assuming only one method present
            return True

        return False

    def _get_routes_with_dependencies(self, route: APIRoute):
        # For restricted routes there needs to be some default parameter
        # in the endpoint, either RoleAuthorization or some function
        # that fetches user like get_current_user.
        # if there are no defaults we default it to an empty list
        route_defaults = route.endpoint.__defaults__ or []
        # functions which require a user in endpoint call
        get_user_deps = {
            get_current_user,
            get_current_user_from_api_key,
            get_current_user_from_multiple_auth,
        }
        # dependencies which filter access based on role or auth
        access_control_deps = (RoleAuthorization, OAuth2PasswordBearer)

        # condition lambdas
        def is_restricted(route):
            return isinstance(route, access_control_deps)

        def is_user_dependant(route):
            return route in get_user_deps

        # get routes with dependencies
        return [
            param.dependency
            for param in route_defaults
            if isinstance(param, Depends)
            and (
                is_restricted(param.dependency)
                or is_user_dependant(param.dependency)
            )
        ]

    def _add_depending_on_role(
        self, role_auth: RoleAuthorization, route: APIRoute
    ):
        user_roles: list[str] = (
            [group.name for group in self.user.groups]
            if self.user is not None
            else []
        )
        user_is_firebase = (
            self.user.auth_mode == AuthMode.FIREBASE if self.user else False
        )
        for role in role_auth.visible_roles:
            if (
                role in user_roles
                or (role_auth.show_for_firebase and user_is_firebase)
            ) or (not self.user and role == "__NOT_A_USER__"):
                self._add_route(route)
                return

    def get_user_routes(self) -> list[APIRoute]:
        # We want to separate routes per role that has access to that route.
        for route in self.app.routes:
            # Force APIRoute type: default for app.routes is List[BaseRoute]
            if type(route) != APIRoute:
                continue  # decide on how to handle this

            # continue on discarded routes
            if self._discard_route(route):
                continue

            # get dependencies from route defaults, add route if empty
            route_deps = self._get_routes_with_dependencies(route)
            if not route_deps:
                self._add_route(route)
                continue

            # loop through routes with dependencies
            for dep in route_deps:
                if isinstance(dep, RoleAuthorization):
                    self._add_depending_on_role(dep, route)

                elif isinstance(dep, OAuth2PasswordBearer) or dep in [
                    get_current_user,
                    get_current_user_from_api_key,
                    get_current_user_from_multiple_auth,
                ]:
                    # This means that route requires authorized user
                    if self.user:
                        self._add_route(route)
        return self.user_routes
