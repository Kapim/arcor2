from typing import Callable

from typed_ast import ast3 as ast

from arcor2.data.common import Project, Scene
from arcor2.parameter_plugins.base import TypesDict, ParameterPlugin
from arcor2.parameter_plugins.integer import get_min_max
from arcor2.data.object_type import ActionParameterMeta


class DoublePlugin(ParameterPlugin):

    @classmethod
    def type(cls):
        return float

    @classmethod
    def type_name(cls) -> str:
        return "double"

    @classmethod
    def meta(cls, param_meta: ActionParameterMeta, action_method: Callable, action_node: ast.FunctionDef) -> None:
        super(DoublePlugin, cls).meta(param_meta, action_method, action_node)
        get_min_max(DoublePlugin, param_meta, action_method, action_node)

    @classmethod
    def value(cls, type_defs: TypesDict, scene: Scene, project: Project, action_id: str, parameter_id: str) -> float:
        return super(DoublePlugin, cls).value(type_defs, scene, project, action_id, parameter_id)