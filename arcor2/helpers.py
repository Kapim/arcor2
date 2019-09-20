from typing import Optional, Dict, Callable, Tuple, Type, Union, Any, Awaitable
from types import ModuleType
import json
import asyncio
import importlib
import re
from dataclasses_jsonschema import ValidationError

import websockets
from aiologger.formatters.base import Formatter  # type: ignore

from arcor2.data.rpc import RPC_MAPPING, Request, Response
from arcor2.data.events import EVENT_MAPPING, Event
from arcor2.exceptions import Arcor2Exception

_first_cap_re = re.compile('(.)([A-Z][a-z]+)')
_all_cap_re = re.compile('([a-z0-9])([A-Z])')

RPC_RETURN_TYPES = Union[None, Tuple[bool, str]]


class ImportClsException(Arcor2Exception):
    pass


def aiologger_formatter() -> Formatter:

    return Formatter('%(name)s - %(levelname)-8s: %(message)s')


def import_cls(module_cls: str) -> Tuple[ModuleType, Type[Any]]:
    """
    Gets module and class based on string like 'module/Cls'.
    :param module_cls:
    :return:
    """

    try:
        module_name, cls_name = module_cls.split('/')
    except (IndexError, ValueError):
        raise ImportClsException("Invalid format.")

    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:
        raise ImportClsException(f"Module '{module_name}' not found.")

    try:
        cls = getattr(module, cls_name)
    except AttributeError:
        raise ImportClsException(f"Class {cls_name} not found in module '{module_name}'.")

    return module, cls


def camel_case_to_snake_case(camel_str: str) -> str:

    s1 = _first_cap_re.sub(r'\1_\2', camel_str)
    return _all_cap_re.sub(r'\1_\2', s1).lower()


def snake_case_to_camel_case(snake_str: str) -> str:

    first, *others = snake_str.split('_')
    return ''.join([first.lower(), *map(str.title, others)])


async def server(client: Any,
                 path: str,
                 logger: Any,
                 register: Callable[[Any], Awaitable[None]],
                 unregister: Callable[[Any], Awaitable[None]],
                 rpc_dict: Dict[Type[Request], Callable[[Request], Awaitable[Response]]],
                 event_dict: Optional[Dict[Type[Event], Callable[[Event], Awaitable[None]]]] = None) -> None:

    if event_dict is None:
        event_dict = {}

    await register(client)
    try:
        async for message in client:

            try:
                data = json.loads(message)
            except json.decoder.JSONDecodeError as e:
                await logger.error(e)
                continue

            if "request" in data:  # ...then it is RPC

                try:
                    req_cls, resp_cls = RPC_MAPPING[data['request']]
                except KeyError:
                    await logger.error(f"Unknown RPC request: {data}.")
                    continue

                if req_cls not in rpc_dict:
                    await logger.debug(f"Ignoring RPC request: {data}.")
                    continue

                try:
                    req = req_cls.from_dict(data)
                except ValidationError as e:
                    await logger.error(f"Invalid RPC: {data}, error: {e}")
                    continue

                resp = await rpc_dict[req_cls](req)

                if resp is None:  # default response
                    resp = resp_cls()
                elif isinstance(resp, tuple):
                    resp = resp_cls(result=resp[0], messages=[resp[1]])
                else:
                    assert isinstance(resp, resp_cls)

                resp.id = req.id

                await asyncio.wait([client.send(resp.to_json())])
                await logger.debug(f"RPC request: {req}, result: {resp}")

            elif "event" in data:  # ...event from UI

                try:
                    event_cls = EVENT_MAPPING[data["event"]]
                except KeyError as e:
                    await logger.error(f"Unknown event type: {e}.")
                    continue

                if event_cls not in event_dict:
                    await logger.debug(f"Ignoring event: {data}.")
                    continue

                try:
                    event = event_cls.from_dict(data)
                except ValidationError as e:
                    await logger.error(f"Invalid event: {data}, error: {e}")
                    continue

                await event_dict[event_cls](event)

            else:
                await logger.error(f"unsupported format of message: {data}")
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        await unregister(client)
