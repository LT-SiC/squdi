class MeasurementController:

    def __init__(self):

        self.measurement_running = False

        # TODO:
        # Connect to the running Qudi instance
        # and obtain references to the required
        # Qudi logic modules.

    def start_measurement(self, parameters):

        if self.measurement_running:
            raise RuntimeError(
                "A measurement is already running"
            )

        self.measurement_running = True

        try:

            print("Starting measurement")

            print(
                "Start voltage:",
                parameters.start_voltage
            )

            print(
                "Stop voltage:",
                parameters.stop_voltage
            )

            print(
                "Number of points:",
                parameters.number_of_points
            )

            print(
                "Integration time:",
                parameters.integration_time
            )

            print(
                "Repetitions:",
                parameters.repetitions
            )

            # TODO:
            # Configure Qudi measurement logic
            # Start the measurement

        except Exception:
            self.measurement_running = False
            raise

    def stop_measurement(self):

        # TODO:
        # Stop the active Qudi measurement

        self.measurement_running = False