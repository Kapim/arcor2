import importlib
import inspect
from typing import List, Optional, Type, Union

import autopep8  # type: ignore
import horast
import typed_astunparse
from typed_ast.ast3 import (
    AST,
    Assert,
    Attribute,
    Call,
    ClassDef,
    Expr,
    FunctionDef,
    ImportFrom,
    Load,
    Module,
    Name,
    NodeTransformer,
    NodeVisitor,
    Raise,
    Store,
    alias,
    fix_missing_locations,
)

from arcor2.source import SourceException


def parse(source: str) -> AST:

    try:
        return horast.parse(source)
    except (AssertionError, NotImplementedError, SyntaxError) as e:
        raise SourceException("Failed to parse the code.") from e


def parse_def(type_def: Type) -> AST:
    try:
        return parse(inspect.getsource(type_def))
    except OSError as e:
        raise SourceException("Failed to get the source code.") from e


def find_asserts(tree: FunctionDef) -> List[Assert]:
    class FindAsserts(NodeVisitor):
        def __init__(self) -> None:
            self.asserts: List[Assert] = []

        def visit_Assert(self, node: Assert) -> None:
            self.asserts.append(node)

    ff = FindAsserts()
    ff.visit(tree)

    return ff.asserts


def find_function(name: str, tree: Union[Module, AST]) -> FunctionDef:
    class FindFunction(NodeVisitor):
        def __init__(self) -> None:
            self.function_node: Optional[FunctionDef] = None

        def visit_FunctionDef(self, node: FunctionDef) -> None:
            if node.name == name:
                self.function_node = node
                return

            if not self.function_node:
                self.generic_visit(node)

    ff = FindFunction()
    ff.visit(tree)

    if ff.function_node is None:
        raise SourceException(f"Function {name} not found.")

    return ff.function_node


def find_class_def(name: str, tree: Union[Module, AST]) -> ClassDef:
    class FindClassDef(NodeVisitor):
        def __init__(self) -> None:
            self.cls_def_node: Optional[ClassDef] = None

        def visit_ClassDef(self, node: ClassDef) -> None:
            if node.name == name:
                self.cls_def_node = node
                return

            if not self.cls_def_node:
                self.generic_visit(node)

    ff = FindClassDef()
    ff.visit(tree)

    if ff.cls_def_node is None:
        raise SourceException(f"Class definition {name} not found.")

    return ff.cls_def_node


def add_import(node: Module, module: str, cls: str, try_to_import: bool = True) -> None:
    """Adds "from ... import ..." to the beginning of the script.

    Parameters
    ----------
    node
    module
    cls

    Returns
    -------
    """

    class AddImportTransformer(NodeTransformer):
        def __init__(self, module: str, cls: str) -> None:
            self.done = False
            self.module = module
            self.cls = cls

        def visit_ImportFrom(self, node: ImportFrom) -> ImportFrom:
            if node.module == self.module:

                for aliass in node.names:
                    if aliass.name == self.cls:
                        self.done = True
                        break
                else:
                    node.names.append(alias(name=self.cls, asname=None))
                    self.done = True

            return node

    if try_to_import:

        try:
            imported_mod = importlib.import_module(module)
        except ModuleNotFoundError as e:
            raise SourceException(e)

        try:
            getattr(imported_mod, cls)
        except AttributeError as e:
            raise SourceException(e)

    tr = AddImportTransformer(module, cls)
    node = tr.visit(node)

    if not tr.done:
        node.body.insert(0, ImportFrom(module=module, names=[alias(name=cls, asname=None)], level=0))


def append_method_call(body: List, instance: str, method: str, args: List, kwargs: List) -> None:
    body.append(Expr(value=Call(func=get_name_attr(instance, method), args=args, keywords=kwargs)))


def get_name(name: str) -> Name:
    return Name(id=name, ctx=Load())


def get_name_attr(name: str, attr: str, ctx: Union[Type[Load], Type[Store]] = Load) -> Attribute:
    return Attribute(value=get_name(name), attr=attr, ctx=ctx())


def tree_to_str(tree: AST) -> str:
    # TODO why this fails?
    # validator.visit(tree)

    fix_missing_locations(tree)
    generated_code: str = horast.unparse(tree)
    generated_code = autopep8.fix_code(generated_code, options={"aggressive": 1})

    return generated_code


def dump(tree: Module) -> str:
    return typed_astunparse.dump(tree)


def find_raises(tree: FunctionDef) -> List[Raise]:
    class FindRaises(NodeVisitor):
        def __init__(self) -> None:
            self.raises: List[Raise] = []

        def visit_Raise(self, node: Raise) -> None:
            self.raises.append(node)

    ff = FindRaises()
    ff.visit(tree)

    return ff.raises
