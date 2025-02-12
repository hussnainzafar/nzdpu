from typing import Any, Generator


class BatchMixin:
    def __init__(self, batch_size: int, *args, **kwargs):
        self.batch_size = batch_size
        super().__init__(*args, **kwargs)

    def batch(self, items: list[Any]) -> Generator[Any, None, None]:
        num_batches = len(items) // self.batch_size
        for i in range(num_batches):
            start = i * self.batch_size
            end = start + self.batch_size
            yield items[start:end]

        if len(items) % self.batch_size != 0:
            start = num_batches * self.batch_size
            yield items[start:]
