"""Vencimientos deterministas; el host decide cuándo invocar tick, sin sleep largo."""
class TaskService:
    def __init__(self, runner, resources):
        self.runner = runner
        self.resources = tuple(dict.fromkeys(resources))

    def tick(self):
        return [result for resource in self.resources if (result := self.runner.tick(resource)) is not None]
