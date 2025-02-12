class DownloadExceedMaximumException(Exception):
    def __init__(self, company_count: int, message: str):
        self.company_count = company_count
        self.message = message
        super().__init__()
