# status_code is the HTTP code the API should send back
class IntegrationError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code
