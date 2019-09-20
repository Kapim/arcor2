#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import asyncio
import json
import functools
import sys
from typing import Union, Set, Callable, Dict
import os
import tempfile
import zipfile
import shutil

import websockets
from websockets.server import WebSocketServerProtocol
from aiologger import Logger  # type: ignore

from arcor2.helpers import server, aiologger_formatter, RPC_RETURN_TYPES
from arcor2.source.utils import make_executable
from arcor2.persistent_storage import AioPersistentStorage
from arcor2.settings import PROJECT_PATH
from arcor2.data.rpc import RunProjectRequest, StopProjectRequest, StopProjectResponse, \
    PauseProjectRequest, PauseProjectResponse, ResumeProjectRequest, ResumeProjectResponse, RPC_MAPPING
from arcor2.data.events import Event, ProjectStateEvent, ProjectStateEventData, ProjectStateEnum

logger = Logger.with_default_handlers(name='manager', formatter=aiologger_formatter())

PROCESS: Union[asyncio.subprocess.Process, None] = None
TASK = None

CLIENTS: Set = set()

STORAGE_CLIENT = AioPersistentStorage()


def process_running() -> bool:

    return PROCESS is not None and PROCESS.returncode is None


async def read_proc_stdout() -> None:

    logger.info("Reading script stdout...")

    assert PROCESS is not None
    assert PROCESS.stdout is not None

    await send_to_clients(ProjectStateEvent(data=ProjectStateEventData(ProjectStateEnum.RUNNING)))

    while process_running():
        try:
            stdout = await PROCESS.stdout.readuntil()
        except asyncio.streams.IncompleteReadError:
            break

        try:
            data = json.loads(stdout.decode("utf-8").strip())
            await send_to_clients(data)
        except json.decoder.JSONDecodeError as e:
            await logger.error(e)

    await send_to_clients(ProjectStateEvent(data=ProjectStateEventData(ProjectStateEnum.STOPPED)))

    logger.info(f"Process finished with returncode {PROCESS.returncode}.")


async def project_run(req: RunProjectRequest) -> Union[RunProjectRequest, RPC_RETURN_TYPES]:

    global PROCESS
    global TASK

    if process_running():
        return False, "Already running!"

    with tempfile.TemporaryDirectory() as tmpdirname:

        path = os.path.join(tmpdirname, "project.zip")

        await STORAGE_CLIENT.publish_project(req.args.id, path)

        with zipfile.ZipFile(path, 'r') as zip_ref:
            zip_ref.extractall(tmpdirname)

        shutil.rmtree(PROJECT_PATH)
        shutil.move(os.path.join(tmpdirname, "arcor2_project"), PROJECT_PATH)

    script_path = os.path.join(PROJECT_PATH, "script.py")
    make_executable(script_path)

    path = os.path.join(PROJECT_PATH, "script.py")

    await logger.info(f"Starting script: {path}")
    PROCESS = await asyncio.create_subprocess_exec(path, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                                                   stderr=asyncio.subprocess.STDOUT)
    if PROCESS.returncode is not None:
        return False, "Failed to start project."
    TASK = asyncio.ensure_future(read_proc_stdout())  # run task in background


async def project_stop(req: StopProjectRequest) -> Union[StopProjectResponse, RPC_RETURN_TYPES]:

    if not process_running():
        return False, "Project not running."

    assert PROCESS is not None
    assert TASK is not None

    await logger.info("Terminating process")
    PROCESS.terminate()
    await logger.info("Waiting for process to finish...")
    await asyncio.wait([TASK])


async def project_pause(req: PauseProjectRequest) -> Union[PauseProjectResponse, RPC_RETURN_TYPES]:

    if not process_running():
        return False, "Project not running."

    assert PROCESS is not None
    assert PROCESS.stdin is not None

    # TODO check if it is not already paused

    PROCESS.stdin.write("p\n".encode())
    await PROCESS.stdin.drain()
    return None


async def project_resume(req: ResumeProjectRequest) -> Union[ResumeProjectResponse, RPC_RETURN_TYPES]:

    if not process_running():
        return False, "Project not running."

    assert PROCESS is not None and PROCESS.stdin is not None

    # TODO check if paused

    PROCESS.stdin.write("r\n".encode())
    await PROCESS.stdin.drain()
    return None


async def send_to_clients(event: Event) -> None:

    if CLIENTS:
        data = event.to_json()
        await asyncio.wait([client.send(data) for client in CLIENTS])


async def register(websocket: WebSocketServerProtocol) -> None:

    await logger.info("Registering new client")
    CLIENTS.add(websocket)
    # TODO send current state


async def unregister(websocket: WebSocketServerProtocol) -> None:
    await logger.info("Unregistering client")
    CLIENTS.remove(websocket)

RPC_DICT: Dict[str, Callable] = {'runProject': project_run,
                                 'stopProject': project_stop,
                                 'pauseProject': project_pause,
                                 'resumeProject': project_resume}

for key in RPC_DICT.keys():
    assert key in RPC_MAPPING


def main() -> None:

    assert sys.version_info >= (3, 6)

    bound_handler = functools.partial(server, logger=logger, register=register, unregister=unregister,
                                      rpc_dict=RPC_DICT)
    asyncio.get_event_loop().set_debug(enabled=True)
    asyncio.get_event_loop().run_until_complete(
        websockets.serve(bound_handler, '0.0.0.0', 6790))
    asyncio.get_event_loop().run_forever()


if __name__ == "__main__":
    main()
