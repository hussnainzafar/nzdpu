import io


class CompanyDownloadOutput:
    def __init__(self, file_stream: io.BytesIO, filename: str):
        self.file_stream = file_stream
        self.filename = filename
