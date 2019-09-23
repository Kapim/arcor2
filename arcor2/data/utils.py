import inspect

from apispec import APISpec  # type: ignore
from apispec_webframeworks.flask import FlaskPlugin  # type: ignore
from apispec.exceptions import DuplicateComponentNameError  # type: ignore
from dataclasses_jsonschema.apispec import DataclassesPlugin

import arcor2.data.rpc
import arcor2.data.common
import arcor2.data.object_type
from dataclasses_jsonschema import JsonSchemaMixin


def generate_swagger() -> str:

    # Create an APISpec
    spec = APISpec(
        title="ARCOR2 Data Models",
        version="1.0.0",
        openapi_version="3.0.2",
        plugins=[FlaskPlugin(), DataclassesPlugin()],
    )

    for module in (arcor2.data.common, arcor2.data.object_type, arcor2.data.rpc):
        for name, obj in inspect.getmembers(module):

            if not inspect.isclass(obj) or not issubclass(obj, JsonSchemaMixin) or obj == JsonSchemaMixin:
                continue

            try:
                spec.components.schema(obj.__name__, schema=obj)
            except DuplicateComponentNameError:
                continue

    return spec.to_yaml()