from fastapi import FastAPI, HTTPException

from models import MeasurementParameters
from measurement_controller import MeasurementController

app = FastAPI(
    title="Qudi Experiment API",
    version="1.0"
)

controller = MeasurementController()


@app.get("/")
def home():
    return {
        "status": "online",
        "message": "Qudi API is running"
    }


@app.get("/status")
def get_status():

    return {
        "measurement_running":
            controller.measurement_running
    }


@app.post("/measurement/start")
def start_measurement(
    parameters: MeasurementParameters
):

    try:

        controller.start_measurement(parameters)

        return {
            "status": "success",
            "message": "Measurement started"
        }

    except RuntimeError as error:

        raise HTTPException(
            status_code=409,
            detail=str(error)
        )

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )


@app.post("/measurement/stop")
def stop_measurement():

    controller.stop_measurement()

    return {
        "status": "success",
        "message": "Stop command sent"
    }