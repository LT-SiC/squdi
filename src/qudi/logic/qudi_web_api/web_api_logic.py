
import json
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path
from hmac import compare_digest

import uvicorn

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from PySide6 import QtCore

from qudi.core.connector import Connector
from qudi.core.configoption import ConfigOption
from qudi.core.module import LogicBase


class MeasurementRequest(BaseModel):
    """Parameters received from the web interface."""

    measurement_type: str
    parameters: dict


class WebApiLogic(LogicBase):
    """
    HTTP interface for submitting measurements to Qudi.

    Receives measurement parameters, creates a measurement
    script and forwards the filename to queue_logic.
    """

    # -------------------------------------------------
    # Qudi configuration
    # -------------------------------------------------

    _queue_logic = Connector(
        name="queue_logic",
        interface="QueueLogic"
    )

    _host = ConfigOption(
        name="host",
        default="0.0.0.0",
        missing="warn"
    )

    _port = ConfigOption(
        name="port",
        default=8000,
        missing="warn"
    )

    _measurement_directory = ConfigOption(
        name="measurement_directory",
        default="",
        missing="warn"
    )

    _api_token = ConfigOption(
        name="api_token",
        default="",
        missing="warn"
    )

    # -------------------------------------------------
    # Qt signals
    # -------------------------------------------------

    sigStartMeasurement = QtCore.Signal(str)

    # -------------------------------------------------
    # Initialization
    # -------------------------------------------------

    def on_activate(self):

        self.log.info("Activating Web API logic")

        self._server = None
        self._server_thread = None

        self._last_submission = {
            "status": "idle",
            "filename": None,
            "timestamp": None
        }

        # Connect the API logic to the existing queue logic.
        # The signal ensures thread-safe communication.
        self.sigStartMeasurement.connect(
            self._queue_logic().start_measurement
        )

        # Prepare measurement directory.
        self.measurement_directory = Path(
            self._measurement_directory
        ).expanduser().resolve()

        self.measurement_directory.mkdir(
            parents=True,
            exist_ok=True
        )

        # Create FastAPI application.
        self.app = self._create_api()

        # Start HTTP server in a separate thread.
        self._start_server()

    # -------------------------------------------------
    # FastAPI setup
    # -------------------------------------------------

    def _create_api(self):

        app = FastAPI(
            title="Qudi Web API",
            version="1.0"
        )

        @app.get("/")
        async def home():

            return {
                "status": "online",
                "message": "Qudi Web API is running"
            }

        @app.post("/measurement/submit")
        async def submit_measurement(
            request: MeasurementRequest,
            authorization: str = Header(default="")
        ):

            self._check_authentication(authorization)

            try:

                # Generate measurement file.
                filename = self._create_measurement_file(
                    request.measurement_type,
                    request.parameters
                )

                # Forward measurement filename to queue_logic.
                self.sigStartMeasurement.emit(
                    str(filename)
                )

                self._last_submission = {
                    "status": "submitted",
                    "filename": str(filename),
                    "timestamp": datetime.now().isoformat()
                }

                self.log.info(
                    f"Measurement submitted: {filename}"
                )

                return {
                    "status": "success",
                    "message": "Measurement submitted",
                    "filename": filename.name
                }

            except Exception as error:

                self.log.exception(
                    "Error submitting measurement"
                )

                raise HTTPException(
                    status_code=500,
                    detail=str(error)
                )

        @app.get("/measurement/status")
        async def measurement_status(
            authorization: str = Header(default="")
        ):

            self._check_authentication(authorization)

            return self._last_submission

        return app

    # -------------------------------------------------
    # Authentication
    # -------------------------------------------------

    def _check_authentication(self, authorization):

        if not self._api_token:
            raise HTTPException(
                status_code=503,
                detail="API authentication token is not configured"
            )

        expected = f"Bearer {self._api_token}"

        if not compare_digest(authorization, expected):

            raise HTTPException(
                status_code=401,
                detail="Invalid API token"
            )

    # -------------------------------------------------
    # Measurement file generation
    # -------------------------------------------------

    def _create_measurement_file(
        self,
        measurement_type,
        parameters
    ):
        """
        Generate a measurement script from received parameters.

        IMPORTANT:
        Adapt render_measurement_script() to the format
        expected by your existing queue_logic.
        """

        filename = (
            f"web_measurement_{uuid.uuid4().hex[:12]}.py"
        )

        filepath = (
            self.measurement_directory / filename
        )

        script_content = self.render_measurement_script(
            measurement_type,
            parameters
        )

        # Atomic file creation: the queue never sees
        # a partially written measurement script.
        temporary_path = filepath.with_suffix(".tmp")

        temporary_path.write_text(
            script_content,
            encoding="utf-8"
        )

        temporary_path.replace(filepath)

        return filepath

    def render_measurement_script(
        self,
        measurement_type,
        parameters
    ):
        """
        Convert measurement parameters into a Python script.

        Replace this example with your actual measurement
        script template.
        """

        supported_types = {
            "voltage_sweep"
        }

        if measurement_type not in supported_types:
            raise ValueError(
                f"Unsupported measurement type: {measurement_type}"
            )

        parameters_json = json.dumps(
            parameters,
            indent=4,
            allow_nan=False
        )

        script = f'''"""
Automatically generated measurement script.
Created by Qudi Web API.
"""

PARAMETERS = {parameters_json}

MEASUREMENT_TYPE = {measurement_type!r}

# TODO:
# Insert the actual measurement routine here.
# Use PARAMETERS to configure the experiment.
'''

        return script

    # -------------------------------------------------
    # HTTP server
    # -------------------------------------------------

    def _start_server(self):

        config = uvicorn.Config(
            app=self.app,
            host=self._host,
            port=self._port,
            log_level="info",
            access_log=False
        )

        self._server = uvicorn.Server(config)

        self._server_thread = threading.Thread(
            target=self._server.run,
            name="QudiWebAPIServer",
            daemon=True
        )

        self._server_thread.start()

        self.log.info(
            f"Qudi Web API starting on "
            f"{self._host}:{self._port}"
        )

    # -------------------------------------------------
    # Deactivation
    # -------------------------------------------------

    def on_deactivate(self):

        self.log.info("Stopping Qudi Web API")

        if self._server is not None:
            self._server.should_exit = True
        if self._server_thread is not None:
            self._server_thread.join(timeout=10)
            if self._server_thread.is_alive():
                self.log.error(
                    "API server thread did not stop within 10 seconds"
                )
        self.sigStartMeasurement.disconnect()
        self.log.info("Qudi Web API stopped")
