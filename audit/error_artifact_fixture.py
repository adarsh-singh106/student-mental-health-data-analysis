"""A joblib-loadable pipeline substitute used only by the error-logging audit."""


class CrashingPipeline:
    def predict(self, rows):
        raise RuntimeError("intentional error-audit failure")
